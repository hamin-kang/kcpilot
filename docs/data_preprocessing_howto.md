# 데이터 전처리 방법

> 이 문서는 D1 전처리 파이프라인의 **실습 가이드이자 코드 SSOT**다 — `preprocess.py`, `ingest.py` 수정, `retrieve_node` 필터의 확정 코드가 여기 있다. 데이터 출처(법령 API)·A종/B종 구분·로드맵 같은 **개념·배경**은 [data_pipeline.md](data_pipeline.md)를 참조한다.

## 0. 선행 개념 3가지
### ① 전처리(preprocessing)
원본 데이터를 임베딩·검색에 적합한 형태로 정제하는 과정. 법령 원문에는 `<개정 2025. 10. 1.>` 같은 개정 이력 마커가 포함돼 있는데, 사람에게는 의미 있는 메타정보지만 임베딩·검색에는 노이즈로 작용한다. 이런 노이즈를 임베딩 직전에 제거하는 작업이다.

### ② 파이프라인(pipeline)
데이터를 정해진 순서의 처리 단계로 통과시키는 자동화 흐름.

```
원문 적재  →  전처리(preprocessing)  →  청킹(chunking)  →  벡터 적재(ingest)
```

한 번 정의해두면 새 법령도 동일한 단계를 거쳐 처리되므로, 수작업 반복이 사라진다. 이번 작업이 이 파이프라인을 구축하는 일이다.

### ③ 임베딩·벡터·유사도 ← 핵심
"왜 별표를 분할하는지"의 근거가 되는 개념이다.

- **임베딩(embedding):** 텍스트의 의미를 고정 길이 실수 벡터로 변환하는 것. (이 프로젝트는 Gemini가 텍스트 1건을 768차원 벡터로 변환한다 — `EMBEDDING_DIM=768`)
- 의미가 유사한 텍스트는 벡터 공간에서 거리가 가깝다. 이 거리를 측정하는 지표가 코사인 유사도(cosine similarity)다. (1에 가까울수록 유사, 0에 가까울수록 무관).
- 사용자가 "헤어드라이어 1200W"로 질의하면 벡터 거리가 가까운 법령이 검색된다. 이것이 RAG의 검색(retrieval) 단계다.

**희석 문제(dilution):**

> 한 문서에 수십 개 품목이 섞여 있으면 그 문서의 임베딩 벡터는 여러 의미가 뭉뚱그려져(엄밀한 산술평균은 아니지만 직관적으로 "섞여 흐려져"), 특정 품목과의 유사도가 모호해진다. 품목 수가 늘수록 무관한 별표가 더 높은 유사도로 검색되는 오류도 발생한다.

`02_안전_시행규칙_별표3.md`가 이 상태다(삭제 항목 빼도 ~30여 개 품목이 단일 문서). **해결책:** 품목 1개 = 문서 1개로 청킹한다. 그러면 각 문서의 임베딩이 단일 품목 의미에 수렴해 정확히 검색된다. 3단계에서 별표를 분할하는 이유다.

---

## 작업 전체 개요

```
1단계  preprocess.py 작성        — 본문 정제 함수 (cleaning)
2단계  frontmatter 작성          — 메타데이터 부여
3단계  별표 분할                 — 품목 1개 = 파일 1개 (chunking)
4단계  ingest.py 수정            — 정제 함수를 적재 파이프라인에 연결
5단계  retrieve_node 수정        — 검색에 카테고리 필터 적용
6단계  검증                      — 검색 결과 확인
```

> 작업 대상은 전부 `ai-service/` 하위다. 명령은 `cd ai-service` 상태를 가정한다.

---

## 1단계 — 본문 정제 함수 작성 (`preprocess.py`)

### [목적]
법령 원문에는 검색을 방해하는 노이즈가 섞여 있다. 실제 파일에서 발췌한 예:

- `<개정 2025. 10. 1.>` ← 개정 이력 마커. 검색에 불필요.
- `1) 삭제 <2026. 4. 1.>` ← 삭제된 조항. 남겨두면 폐지된 규정이 검색된다.
- `기계ㆍ기구` ← 가운뎃점이 표준 `·`가 아닌 변종 `ㆍ`. 표기를 통일해야 검색이 안정적이다.

이를 임베딩 **전에** 제거한다.

### [작업]
`ai-service/preprocess.py` 파일을 생성하고, 본문을 받아 정제된 문자열을 반환하는 `clean_legal_text()` 함수를 작성한다.

### [코드 전체]
아래를 그대로 `ai-service/preprocess.py`로 저장한다. (각 줄의 의미는 코드 아래에서 설명)

```python
"""법령 본문 전처리 모듈.

ingest.py가 임베딩 직전에 이 모듈의 clean_legal_text()를 호출한다.
원문에 섞인 노이즈(개정 마커, 삭제 항목, 비표준 특수문자)를 제거하는 게 목적이다.

단독 실행으로 동작을 확인할 수 있다:
    uv run python preprocess.py
"""
from __future__ import annotations

import re
import unicodedata

# "<개정 2025. 10. 1.>", "<신설 ...>", "<시행일 ...>" 같은 인라인 마커 패턴
_REVISION_MARK = re.compile(r"<\s*(개정|신설|시행일|본조신설|제목개정|전문개정)[^>]*>")

# "1) 삭제 <2026. 4. 1.>", "가. 삭제 <...>" 처럼 통째로 삭제된 항목 '줄' 패턴
_DELETED_LINE = re.compile(r"^\s*(?:\d+\)|[가-힣]\.)\s*삭제\s*<[^>]*>\s*$")


def _normalize_chars(text: str) -> str:
    """문자 표기를 정규화한다."""
    text = unicodedata.normalize("NFC", text)         # 자모 분해(NFD) → 조합형(NFC)
    text = text.replace("\u3000", " ")             # 전각 공백 → 일반 공백
    text = text.replace("ㆍ", "·").replace("‧", "·")   # 가운뎃점 변종 → 표준 가운뎃점
    return text


def clean_legal_text(text: str) -> str:
    """법령 본문에서 검색 노이즈를 제거한다."""
    kept: list[str] = []
    for line in text.splitlines():
        if _DELETED_LINE.match(line):        # ① 삭제 항목 줄은 통째로 제거
            continue
        line = _REVISION_MARK.sub("", line)   # ② 인라인 <개정 ...> 마커 제거
        kept.append(line.rstrip())            # ③ 줄 끝 공백 제거
    text = "\n".join(kept)
    text = _normalize_chars(text)             # ④ 특수문자 정규화
    text = re.sub(r"\n{3,}", "\n\n", text)    # ⑤ 빈 줄 3개 이상이면 2개로 축소
    return text.strip()


# 직접 실행 시 샘플 before/after 출력 (동작 검증용)
if __name__ == "__main__":
    sample = (
        "제5조(안전인증 등) ① ... 안전인증을 받아야 한다. <개정 2025. 10. 1.>\n"
        "사. 전기기기:\n"
        "1) 삭제 <2026. 4. 1.>\n"
        "5) 모발관리기\n"
        "비고) 기계ㆍ기구에 부착되는 특수구조인 것은 제외한다."
    )
    print("===== BEFORE =====")
    print(sample)
    print("\n===== AFTER =====")
    print(clean_legal_text(sample))
```

### [코드 해설 — 정규식]
정규식(`re`)은 "특정 패턴의 문자열을 찾아라"를 기술하는 패턴 언어다.

- `_REVISION_MARK` 패턴 `<\s*(개정|신설|...)[^>]*>`:
  - `<`, `>` : 꺾쇠 문자 자체
  - `\s*` : 공백 0개 이상
  - `(개정|신설|...)` : 괄호 안 단어 중 하나로 시작
  - `[^>]*` : `>`가 아닌 문자 0개 이상 (날짜 등 내부 내용)
  - → `<개정 ...>`, `<신설 ...>` 마커 전체를 매칭해 `.sub("", line)`으로 빈 문자열로 치환(제거)한다.
- `_DELETED_LINE` 패턴 `^\s*(?:\d+\)|[가-힣]\.)\s*삭제\s*<[^>]*>\s*$`:
  - `^`, `$` : 줄의 시작·끝 (줄 전체가 이 형태일 때만 매칭)
  - `\d+\)` : 숫자 + 닫는 괄호 → `1)`, `12)`
  - `[가-힣]\.` : 한글 1자 + 마침표 → `가.`, `나.`
  - `삭제` : 리터럴
  - → `1) 삭제 <2026. 4. 1.>` 같은 **줄 전체**를 매칭해 `continue`로 제거한다.
- `unicodedata.normalize("NFC", text)` : macOS에서 한글이 자모 분해(NFD) 형태로 들어올 수 있어, 조합형(NFC)으로 정규화한다. (파일명 영문화와 동일한 NFD 이슈)

### [실행]
함수를 단독 실행해 동작을 먼저 검증한다.

```bash
cd ai-service
uv run python preprocess.py
```

### [기대 출력]
```
===== BEFORE =====
제5조(안전인증 등) ① ... 안전인증을 받아야 한다. <개정 2025. 10. 1.>
사. 전기기기:
1) 삭제 <2026. 4. 1.>
5) 모발관리기
비고) 기계ㆍ기구에 부착되는 특수구조인 것은 제외한다.

===== AFTER =====
제5조(안전인증 등) ① ... 안전인증을 받아야 한다.
사. 전기기기:
5) 모발관리기
비고) 기계·기구에 부착되는 특수구조인 것은 제외한다.
```

`<개정 ...>` 제거, `1) 삭제 ...` 줄 제거, `ㆍ` → `·` 치환이 확인되면 정상이다.

### [문제 해결]
- `ModuleNotFoundError` → `ai-service` 디렉토리에서 `uv run`으로 실행했는지 확인.
- AFTER가 BEFORE와 동일 → 정규식을 오타 없이 복사했는지, 특히 백슬래시(`\`) 누락 여부 확인.

---

## 2단계 — 메타데이터 부여 (`frontmatter`)

### [목적]
검색 시 "전기용품 법령만"처럼 **범위를 제한하려면**, 각 파일에 분류 정보(전기용품 / 안전 축 / 안전인증대상)가 메타데이터로 부여돼 있어야 한다. 이 메타데이터가 `frontmatter`(파일 최상단 `---`로 감싼 블록)다. 현재 필드는 4개(`law/article/axis/category`)이며, 6개를 추가한다.

### [작업]
`data/legal/`의 각 `.md` 파일 최상단 frontmatter에 필드를 추가한다. **본문은 수정하지 않는다.**

### [파일 Before / After]
`01_안전_안전관리법_제5조.md` (영문명: `01_safety_act_art5.md`)

**Before:**
```yaml
---
law: 전기용품 및 생활용품 안전관리법
article: 제5조(안전인증 등)
axis: 안전
category: 전기용품
---

제5조(안전인증 등) ① ...
```

**After:**
```yaml
---
doc_type: 법률
axis: 안전
category: 전기용품
cert_level: 안전인증
law_name: 전기용품 및 생활용품 안전관리법
article: 제5조(안전인증 등)
effective_date: 2025-10-01
source_url: https://www.law.go.kr/법령/전기용품및생활용품안전관리법
---

제5조(안전인증 등) ① ...
```

> 참고: 기존 `law:` 키를 `law_name:`으로 변경했다. 4단계에서 `ingest.py`도 이에 맞춰 수정한다. 혼동되면 `law:`와 `law_name:`을 둘 다 기재해도 된다(양쪽 모두 읽도록 처리 가능).

### [필드 정의]
| 필드 | 의미 | 예시 |
|---|---|---|
| `doc_type` | 문서 종류 | 법률 / 시행령 / 시행규칙 / 별표 / 안전기준고시 |
| `axis` | 인증 축 | 안전 / 전자파 |
| `category` | 제품 카테고리 (필터 기준) | 전기용품 / 생활용품 / 어린이제품 |
| `cert_level` | 인증 수준 | 안전인증 / 안전확인 / 공급자적합성확인 / 적합등록 … |
| `effective_date` | 시행일 (개정 추적·정보 기준일) | 2025-10-01 |
| `source_url` | 원문 URL (출처 표시 F-07) | https://… |

> **`effective_date` 산정:** 1단계에서 제거한 본문 `<개정 2025. 10. 1.>`의 날짜가 곧 시행일이다. 원문에서 최신 개정일을 확인해 `2025-10-01` 형식으로 기재한다.

현재 파일이 6개뿐이므로 frontmatter는 **수동으로** 작성하는 게 가장 확실하다.

---

## 3단계 — 별표 분할 (품목 1개 = 파일 1개)

### [목적]
0단계 ③의 **희석 문제** 때문이다. `02_..._별표3.md`는 ~30여 개 품목(삭제 제외)이 단일 문서라 "헤어드라이어" 검색의 유사도가 모호하다. 품목 단위로 분할하면 유사도가 또렷해진다.

### [작업]
**시연 대상 품목만** 선별해 품목당 파일 1개로 분리한다. (전 품목을 분할할 필요는 없다 — 시연에 쓰지 않는 품목은 인덱싱 대상이 아니다)

### [절차 — 수동]
원본을 복제한 뒤 한 품목만 남기고 frontmatter를 작성한다.

```bash
cd ai-service/data/legal
cp 02_safety_rule_appx3.md 02_safety_rule_appx3_hair-dryer.md
# 새 파일을 편집기로 열어 아래 형태로 수정한다
```

**완성된 `02_safety_rule_appx3_hair-dryer.md`:**
```yaml
---
doc_type: 별표
axis: 안전
category: 전기용품
cert_level: 안전인증
item_code: ELEC-005
item_name: 모발관리기
law_name: 전기용품 및 생활용품 안전관리법 시행규칙
article: 별표 3 (안전인증대상제품)
effective_date: 2026-04-01
source_url: https://www.law.go.kr/...
---

전기용품 및 생활용품 안전관리법 시행규칙 [별표 3]
안전인증대상제품 (제3조제1항 및 제2항 관련)

1. 안전인증대상전기용품
사. 전기기기 — 5) 모발관리기
```

> **주의 (원문 대조 필수):** `cert_level`은 해당 품목이 **어느 별표에 수록됐는지**로 결정된다. 별표 3은 "안전인증대상"이고 모발관리기가 거기 실려 있으므로 `안전인증`이 맞다(requirements 시나리오 A도 "안전인증"). 만약 다른 문서·메모에 "안전확인"으로 적힌 게 보이면 그건 별표 3과 어긋나는 오기이니 **별표 원문 기준으로 통일**하라. (데이터엔 이런 불일치가 흔하므로 원문 대조가 핵심이다.)

> **분할 시 `category` 재지정:** 별표 3 원본은 전기용품과 **생활용품**(자동차용 재생타이어·가스라이터·압력솥)을 한 파일에 담고 통째로 `category: 전기용품`으로 태깅돼 있다. 품목별로 쪼갤 때 각 품목의 **실제 카테고리**를 넣어라 — 생활용품 품목을 전기용품으로 두면 5단계 카테고리 필터가 틀린다.

### [분할 개수]
시연 3종에 필요한 만큼만:
- 헤어드라이어 → `02_safety_rule_appx3_hair-dryer.md` (위)
- 어린이 완구 → 어린이제품 별표에서 해당 품목 1개
- 그 외 데모에서 언급할 품목

### [원본 통합 별표 처리]
시연 품목 분할을 마치면, 원본 통합 파일 `02_safety_rule_appx3.md`는 `legal/` **밖으로 이동**한다(예: `data/_raw/`). `ingest.py`는 `legal/` 내부 `.md`만 로드하므로, 이동시키면 통합 파일이 거대한 단일 청크로 인덱싱되는 것을 방지한다.

```bash
mkdir -p ../_raw
mv 02_safety_rule_appx3.md ../_raw/
```

> 추후 전 품목(241개)이 필요하면 자동 분할 스크립트를 작성한다. MVP 단계에서는 수동 처리가 적절하다.

---

## 4단계 — `ingest.py`에 전처리 연결 + 메타데이터 적재

### [목적]
1단계의 `clean_legal_text()`는 **호출돼야** 동작한다. 적재 단계(`ingest.py`)에 연결해야 모든 법령에 자동 적용된다. 동시에 2단계에서 추가한 메타데이터도 DB에 함께 적재되도록 한다.

### [작업]
`ingest.py`의 `load_law_documents()` 함수를 아래로 **전면 교체**하고, 파일 상단 import에 한 줄 추가한다.

### [코드 전체]
**(1) 파일 상단 import 구역에 추가:**
```python
from preprocess import clean_legal_text
```

**(2) `load_law_documents()` 함수 교체:**
```python
def load_law_documents() -> list[Document]:
    docs: list[Document] = []
    skipped: list[str] = []
    for path in sorted(LEGAL_DIR.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        if not body or body.startswith(PLACEHOLDER_MARK):
            skipped.append(path.name)
            continue

        body = clean_legal_text(body)          # ← ① 전처리 적용 (1단계 함수)

        docs.append(Document(
            page_content=body,
            metadata={
                # 기존 필드 (law_name / law 양쪽 대응)
                "law": meta.get("law_name") or meta.get("law", "(미상)"),
                "article": meta.get("article", ""),
                "axis": meta.get("axis"),
                "category": meta.get("category"),
                # ← ② 신규 필드 (필터링·추적용). frontmatter에 없으면 None으로 적재
                "doc_type": meta.get("doc_type"),
                "cert_level": meta.get("cert_level"),
                "item_code": meta.get("item_code"),
                "item_name": meta.get("item_name"),
                "effective_date": meta.get("effective_date"),
                "source_url": meta.get("source_url"),
            },
        ))
    if skipped:
        print(f"  (미작성 건너뜀: {', '.join(skipped)})")
    return docs
```

변경점은 두 곳이다: ① `body = clean_legal_text(body)` 한 줄, ② metadata 신규 필드 6개.

### [실행]
```bash
cd ai-service
uv run python ingest.py
```

> `ingest.py`는 실행마다 기존 컬렉션을 삭제 후 재적재한다(idempotent). 따라서 여러 번 실행해도 중복이 누적되지 않는다.

### [기대 출력]
```
법령 코퍼스 적재 중...
  [kc_legal] 8건 적재 완료
리콜 사례 적재 중...
  [kc_recalls] 3건 적재 완료

완료. ...
```
(건수는 작성한 파일 수에 따라 달라진다. 별표 분할로 파일이 늘면 그만큼 증가한다.)

### [문제 해결]
- `GOOGLE_API_KEY가 설정되지 않았습니다` → `ai-service/.env`에 키 등록 여부 확인.
- `frontmatter('---')로 시작해야 합니다` → 일부 `.md` 최상단이 `---`로 시작하지 않음. 2·3단계 파일 frontmatter 확인.
- DB 연결 에러 → `docker-compose up -d`로 PostgreSQL 기동 여부 확인.

---

## 5단계 — 검색에 카테고리 필터 적용 (`retrieve_node`)

### [목적]
현재 검색은 법령 전체를 대상으로 한다. 입력 폼에서 이미 "전기 사용=예"를 받았으므로, **전기용품 법령으로 범위를 제한하면** 노이즈가 줄어 정확도가 향상된다.

### [⚠️ 핵심 주의 — 축이 아니라 카테고리로 필터링]
EMC(전자파) 법령도 전부 `category: 전기용품`으로 태깅돼 있다(확인됨). 따라서 **카테고리(전기용품)로 필터링하면** 안전 법령과 전자파 법령이 **둘 다** 남는다. 만약 **축(안전/전자파)으로 필터링하면** 한쪽만 남아 "안전+전자파 동시 인증"을 식별하지 못한다 — 이는 이 서비스의 **핵심 차별점을 훼손하는** 결함이다. 반드시 카테고리로 필터링한다.

### [작업]
`workflow.py`에 헬퍼 함수 `_build_law_filter()`를 추가하고 `retrieve_node()`를 교체한다.

### [코드 전체]
**(1) `retrieve_node` 위에 헬퍼 추가:**
```python
def _build_law_filter(state: AssessmentState) -> dict | None:
    """classify 단계가 결정한 카테고리로 검색 범위를 제한하는 필터를 생성한다.

    축(안전/전자파)이 아니라 category로 필터링한다. 축으로 필터링하면
    '안전+전자파 동시 인증'을 한 번에 식별하지 못해 핵심 기능이 깨진다.
    """
    cats = state.get("categories") or []
    if not cats:
        return None
    return {"category": {"$in": cats}}
```

**(2) `retrieve_node()` 교체:**
```python
def retrieve_node(state: AssessmentState) -> dict:
    req = state["request"]
    query = state.get("search_query") or _product_brief(req)
    store = get_vector_store(settings.LAW_COLLECTION)

    law_filter = _build_law_filter(state)
    pairs = store.similarity_search_with_score(
        query, k=settings.TOP_K_LAW, filter=law_filter
    )
    # 폴백: 필터가 너무 좁아 0건이면 필터를 해제하고 재검색
    if not pairs and law_filter is not None:
        pairs = store.similarity_search_with_score(query, k=settings.TOP_K_LAW)

    hits: list[dict] = []
    for i, (doc, distance) in enumerate(pairs, start=1):
        m = doc.metadata or {}
        hits.append({
            "ref": i,
            "law": m.get("law", "(미상)"),
            "article": m.get("article", ""),
            "axis": m.get("axis"),
            "category": m.get("category"),
            "text": doc.page_content,
            "similarity": round(cosine_distance_to_similarity(distance), 3),
        })

    summary = "; ".join(
        f"[근거{h['ref']}] {h['law']} {h['article']}(유사도 {h['similarity']})" for h in hits
    ) or "검색 결과 없음"
    return {
        "law_hits": hits,
        "reasoning_log": _log(state, "② 법령 검색(RAG)", f"질의='{query}' → {summary}"),
    }
```

변경 핵심은 `filter=law_filter` 한 곳과, 0건 시 재검색하는 **폴백** 3줄이다. 폴백 덕분에 "필터가 과도하게 좁아 결과가 0건"인 최악의 경우를 회피한다.

### [검증]
진단 흐름 내부에서 동작하므로 6단계에서 함께 검증한다.

---

## 6단계 — 검색 결과 검증

### [목적]
적재·필터 적용만으로는 부족하다. **헤어드라이어 질의 시 헤어드라이어 법령이 1순위로 검색되는지** 직접 확인해야 한다.

### [방법 A — 검색 단독 테스트]
아래를 터미널에 붙여넣으면 적재된 데이터의 검색 결과를 즉시 확인할 수 있다.

```bash
cd ai-service
uv run python -c "
from llm import get_vector_store
import settings
store = get_vector_store(settings.LAW_COLLECTION)
pairs = store.similarity_search_with_score('헤어드라이어 220V 1200W 가정용', k=5)
for doc, dist in pairs:
    m = doc.metadata
    name = m.get('item_name') or m.get('article')
    print(round(1-dist, 3), '|', m.get('axis'), m.get('category'), '|', name)
"
```

**기대 출력 (예):**
```
0.71 | 안전 전기용품 | 모발관리기
0.66 | 전자파 전기용품 | 가정용 전기기기 전자파 장해 측정 기준
0.63 | 안전 전기용품 | 제5조(안전인증 등)
...
```
모발관리기(헤어드라이어)와 전자파 기준이 상위에 함께 검색되면, **안전+전자파 동시 식별**의 토대가 마련된 것이다. 별표 분할 전후로 별표의 유사도·순위를 비교하면, 0단계 ③의 희석 문제를 실측으로 확인할 수 있다.

### [방법 B — 전체 진단 실행]
서비스를 기동해 실제 진단을 실행한다.

```bash
# 터미널 1: DB
docker-compose up -d
# 터미널 2: AI 서비스
cd ai-service && uv run uvicorn main:app --reload
```
브라우저에서 `http://localhost:8000/docs`를 열고 `/ai/run-assessment`에 헤어드라이어 정보를 입력해 실행한다. 결과에 안전+전자파 인증이 함께 나오고, 추론 로그 ②번에 검색된 법령이 표시되면 정상이다.

---

## 신규 데이터 추가 절차 (반복 작업)

파이프라인이 구축됐으므로, 신규 법령·품목은 다음 절차만 반복하면 된다:

1. 원문을 `.md` 파일로 작성한다 (`data/legal/`)
2. frontmatter를 작성한다 (2단계 표 참고)
3. 별표는 품목 단위로 분할한다 (3단계)
4. `uv run python ingest.py` 실행 (전처리 자동 적용)
5. 방법 A로 검색 검증

전처리 함수(`clean_legal_text`)·필터·적재 로직은 **이미 구현돼 있으므로 재수정하지 않는다.** 이것이 파이프라인 구축의 목적이다.

---

## 에러 레퍼런스

| 증상 | 원인 | 해결 |
|---|---|---|
| `frontmatter('---')로 시작해야 합니다` | 일부 `.md`가 `---`로 시작하지 않음 | 해당 파일 최상단 `---` 블록 확인 |
| `GOOGLE_API_KEY가 설정되지 않았습니다` | `.env`에 키 없음 | `ai-service/.env`에 `GOOGLE_API_KEY=...` |
| `ingest.py` 실행 시 DB 연결 실패 | PostgreSQL 미기동 | `docker-compose up -d` |
| 무관한 결과가 검색됨 | 별표 미분할 / category 태깅 누락 | 3단계 분할, frontmatter `category` 확인 |
| 검색 결과 0건 | 필터가 과도하게 좁음 | 5단계 폴백이 자동 재검색. frontmatter `category` 값이 classify 결과와 일치하는지 확인 |
| macOS 생성 파일을 CI(Linux)가 못 찾음 | 파일명/내용이 NFD | 파일명 영문화 + 본문은 `clean_legal_text`가 NFC로 정규화 |
| 동일 데이터가 중복 적재된 듯 | — | `ingest.py`는 매 실행 시 컬렉션을 재생성하므로 중복 누적 없음. 재실행하면 됨 |

---

*1~6단계를 완료하면 D1(파이프라인 정립)이 끝난다. 다음은 D2(시연 3종 데이터 확장) — 동일 파이프라인으로 어린이완구·IoT센서 데이터를 처리한다.*
