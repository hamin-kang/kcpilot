"""법령 코퍼스 + 리콜 사례를 pgvector에 적재하는 1회용 스크립트.

실행:
    uv run python ingest.py

재실행하면 기존 컬렉션을 지우고 다시 넣는다(idempotent).

법령은 data/legal/*.md 파일에서 읽는다. 각 파일은 YAML 스타일 frontmatter +
본문으로 구성된다 (법조문처럼 긴 멀티라인 텍스트는 JSON보다 마크다운이 안전하다):

    ---
    law: 전기용품 및 생활용품 안전관리법
    article: 제5조(안전인증 등)
    axis: 안전
    category: 전기용품
    ---

    제5조(안전인증 등) ① ...

본문이 아직 채워지지 않은 placeholder 파일("[여기에"로 시작)은 건너뛴다.
"""
import json
from pathlib import Path

from langchain_core.documents import Document

import settings
from llm import get_vector_store

DATA_DIR = Path(__file__).parent / "data"
LEGAL_DIR = DATA_DIR / "legal"
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


def load_law_documents() -> list[Document]:
    docs: list[Document] = []
    skipped: list[str] = []
    for path in sorted(LEGAL_DIR.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not body or body.startswith(PLACEHOLDER_MARK):
            skipped.append(path.name)
            continue
        docs.append(Document(
            page_content=body,
            metadata={
                "law": meta.get("law", "(미상)"),
                "article": meta.get("article", ""),
                "axis": meta.get("axis"),
                "category": meta.get("category"),
            },
        ))
    if skipped:
        print(f"  (미작성 건너뜀: {', '.join(skipped)})")
    return docs


def load_recall_documents() -> list[Document]:
    raw = json.loads((DATA_DIR / "recalls.json").read_text(encoding="utf-8"))
    docs: list[Document] = []
    for item in raw:
        # 검색 대상 텍스트는 제목+사유를 합친다.
        content = f"{item['title']}\n{item['product']}\n{item['reason']}"
        docs.append(Document(page_content=content, metadata=item))
    return docs


def ingest(collection: str, docs: list[Document]) -> None:
    # pre_delete_collection=True → 재실행 시 깨끗하게 갈아끼움
    store = get_vector_store(collection)
    store.delete_collection()
    store.create_collection()
    store.add_documents(docs)
    print(f"  [{collection}] {len(docs)}건 적재 완료")


def main() -> None:
    if not settings.GOOGLE_API_KEY or settings.GOOGLE_API_KEY.startswith("PUT_"):
        raise SystemExit(
            "GOOGLE_API_KEY가 설정되지 않았습니다. ai-service/.env를 확인하세요."
        )

    print("법령 코퍼스 적재 중...")
    law_docs = load_law_documents()
    ingest(settings.LAW_COLLECTION, law_docs)

    print("리콜 사례 적재 중...")
    recall_docs = load_recall_documents()
    ingest(settings.RECALL_COLLECTION, recall_docs)

    print("\n완료. 검색 테스트는 `uv run python -c \"from workflow import run_assessment; ...\"` 또는 /docs 에서.")


if __name__ == "__main__":
    main()
