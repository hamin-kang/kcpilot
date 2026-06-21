"""전처리된 법령 코퍼스 + 리콜 사례를 pgvector에 적재하는 스크립트.

실행:
    uv run python pipeline/ingest.py

재실행하면 기존 컬렉션을 지우고 다시 넣는다(idempotent).

data/processed/*.md를 읽어 **두 컬렉션**으로 나눠 적재한다. 판별 기준은
frontmatter의 item_name 유무다:

- item_name 없음 → 법령 조문 → kc_legal 컬렉션.
  본문 전체를 임베딩한다(자유형 텍스트라 맥락 검색이 맞다).

- item_name 있음 → 별표 품목 → kc_items 컬렉션.
  품목명만 임베딩한다("헤어드라이어"↔"모발관리기" 매칭 정밀도를 위해). cert_level은
  본문에서 읽지 않고 metadata에서 그대로 꺼내 쓴다(워크플로우의 권위 있는 출처).

각 .md는 YAML 스타일 frontmatter + 본문으로 구성된다:

    ---
    law_name: 전기용품 및 생활용품 안전관리법
    article: 제5조(안전인증 등)
    axis: 안전
    category: 전기용품
    ---

    제5조(안전인증 등) ① ...

본문이 아직 채워지지 않은 placeholder 파일("[여기에"로 시작)은 건너뛴다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from langchain_core.documents import Document

import settings
from llm import get_vector_store
from preprocess import clean_legal_text

DATA_DIR = ROOT / "data"
LEGAL_DIR = DATA_DIR / "processed"
PLACEHOLDER_MARK = "[여기에"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """'---' 로 감싼 frontmatter와 본문을 분리한다."""
    if not text.lstrip().startswith("---"):
        raise ValueError("frontmatter('---')로 시작해야 합니다")
    # 앞쪽 '---' 이후를 두 번만 쪼개 본문에 '---'가 있어도 보존
    _, meta_block, body = text.split("---", 2)
    meta: dict = {}
    for line in meta_block.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, body.strip()


def _common_meta(meta: dict) -> dict:
    """두 컬렉션이 공유하는 metadata."""
    return {
        "law": meta.get("law_name") or meta.get("law", "(미상)"),
        "article": meta.get("article", ""),
        "axis": meta.get("axis"),
        "category": meta.get("category"),
        "doc_type": meta.get("doc_type"),
        "cert_level": meta.get("cert_level"),
        "item_name": meta.get("item_name"),
        "effective_date": meta.get("effective_date"),
        "source_url": meta.get("source_url"),
    }


def load_documents() -> tuple[list[Document], list[Document]]:
    """processed/*.md를 (법령 조문, 별표 품목) 두 묶음으로 나눠 반환한다.

    판별: frontmatter에 item_name이 있으면 품목, 없으면 조문.
    - 조문은 본문 전체를 임베딩한다(맥락 검색).
    - 품목은 품목명만 임베딩한다(매칭 정밀도). 본문은 표시용으로 metadata에 보관.
    """
    legal_docs: list[Document] = []
    item_docs: list[Document] = []
    skipped: list[str] = []
    for path in sorted(LEGAL_DIR.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not body or body.startswith(PLACEHOLDER_MARK):
            skipped.append(path.name)
            continue
        body = clean_legal_text(body)  # 임베딩 전 노이즈 제거 (이중 안전장치)
        item_name = (meta.get("item_name") or "").strip()
        if item_name:
            # 품목: 품목명을 임베딩 대상으로, 본문은 표시용으로 metadata에 보관
            item_docs.append(Document(
                page_content=item_name,
                metadata={**_common_meta(meta), "body": body},
            ))
        else:
            legal_docs.append(Document(
                page_content=body,
                metadata=_common_meta(meta),
            ))
    if skipped:
        print(f"  (미작성 건너뜀: {', '.join(skipped)})")
    return legal_docs, item_docs


def load_recall_documents() -> list[Document]:
    raw = json.loads((DATA_DIR / "recalls.json").read_text(encoding="utf-8"))
    docs: list[Document] = []
    for item in raw:
        # 검색 대상 텍스트는 제목+사유를 합친다.
        content = f"{item['title']}\n{item['product']}\n{item['reason']}"
        docs.append(Document(page_content=content, metadata=item))
    return docs


# Vertex AI 임베딩은 요청당 최대 250건이라 그보다 작게 끊어 적재한다.
EMBED_BATCH = 200


def ingest(collection: str, docs: list[Document]) -> None:
    store = get_vector_store(collection)
    store.delete_collection()  # 재실행 시 깨끗하게 갈아끼움
    store.create_collection()
    for i in range(0, len(docs), EMBED_BATCH):
        store.add_documents(docs[i:i + EMBED_BATCH])
    print(f"  [{collection}] {len(docs)}건 적재 완료")


def main() -> None:
    if not settings.GCP_PROJECT:
        raise SystemExit(
            "GCP_PROJECT가 설정되지 않았습니다. ai-service/.env에 GCP_PROJECT=<프로젝트ID>를 넣으세요."
        )

    print("법령 코퍼스 적재 중...")
    legal_docs, item_docs = load_documents()
    ingest(settings.LAW_COLLECTION, legal_docs)
    ingest(settings.ITEM_COLLECTION, item_docs)

    if (DATA_DIR / "recalls.json").exists():
        print("리콜 사례 적재 중...")
        recall_docs = load_recall_documents()
        ingest(settings.RECALL_COLLECTION, recall_docs)
    else:
        print("리콜 데이터 없음(data/recalls.json 미존재) — 건너뜀")

    print("\n완료. 검색 테스트는 `uv run python -c \"from workflow import run_assessment; ...\"` 또는 /docs 에서.")


if __name__ == "__main__":
    main()
