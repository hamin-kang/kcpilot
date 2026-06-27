"""전처리된 법령 코퍼스 + 리콜 사례를 pgvector에 적재하는 스크립트.

실행:
    uv run python pipeline/ingest.py

재실행하면 기존 컬렉션을 지우고 다시 넣는다(idempotent).

data/processed/*.md를 읽어 **두 컬렉션**으로 나눠 적재한다. 판별 기준은
frontmatter의 item_name 유무다:

- item_name 없음 → 법령 조문 → kc_legal 컬렉션.
  본문 전체를 임베딩한다(자유형 텍스트라 맥락 검색이 맞다).

- item_name 있음 → 별표 품목 → kc_items 컬렉션.
  품목명 + 본문(대표 품목 리스트 포함)을 함께 임베딩한다. item_name만 쓰면
  "이·미용기기류" ↔ "헤어드라이어"처럼 카테고리명과 제품명이 달라 매칭이 안 되는데,
  본문에 "전기드라이기(머리, 손톱 포함)" 같은 대표 품목이 포함되면 해결된다.
  cert_level은 본문에서 읽지 않고 metadata에서 그대로 꺼낸다(권위 있는 출처).

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
import re
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

_REP_PRODUCTS_RE = re.compile(
    r"대표적인 품목은 다음과 같다[.\-\s]+(.+?)(?=적합성평가|$)", re.DOTALL
)


def _rep_keywords(body: str) -> str:
    """body에서 '대표적인 품목은 다음과 같다' 뒤의 첫 5개 제품명을 추출한다.

    '이·미용기기류' 같은 광범위한 카테고리명만으로는 '헤어드라이어'와 매칭이 안 되는데,
    본문의 대표 품목 리스트('전기드라이기(머리, 손톱 포함)' 등)를 임베딩 텍스트에 포함하면
    검색 정확도가 크게 올라간다.
    """
    m = _REP_PRODUCTS_RE.search(body)
    if not m:
        return ""
    parts = re.split(r"[,，\n]", m.group(1).strip())[:5]
    names = [re.sub(r"\(.*?\)", "", p).strip(" -·\t") for p in parts]
    return ", ".join(n for n in names if len(n) > 1)


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
    - 품목은 품목명 + 본문을 함께 임베딩한다. 카테고리명("이·미용기기류")만으론
      개별 제품명("헤어드라이어")과 매칭이 안 되지만, 본문의 대표 품목 리스트를
      포함하면 "전기드라이기(머리, 손톱 포함)"가 검색에 반영된다.
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
            # 품목: 카테고리명 + 대표 품목 키워드 + 본문을 임베딩한다.
            # 카테고리명("이·미용기기류")만으론 "헤어드라이어"와 매칭이 안 되지만,
            # 대표 품목 키워드("전기드라이기, 전기고데기")를 앞에 붙이면
            # 임베딩 공간에서 제품명과 직접 연결된다.
            keywords = _rep_keywords(body)
            embed_text = f"{item_name} {keywords}\n{body}" if keywords else f"{item_name}\n{body}"
            item_docs.append(Document(
                page_content=embed_text,
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


def load_recall_documents(path: Path) -> list[Document]:
    raw = json.loads(path.read_text(encoding="utf-8"))
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

    recall_file = DATA_DIR / "raw" / "recalls" / "recalls.json"
    if recall_file.exists():
        print("리콜 사례 적재 중...")
        recall_docs = load_recall_documents(recall_file)
        ingest(settings.RECALL_COLLECTION, recall_docs)
    else:
        print("리콜 데이터 없음(data/raw/recalls/recalls.json 미존재) — 건너뜀")

    print("\n완료. 검색 테스트는 `uv run python -c \"from workflow import run_assessment; ...\"` 또는 /docs 에서.")


if __name__ == "__main__":
    main()
