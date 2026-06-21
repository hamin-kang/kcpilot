# 데이터 전처리 파이프라인

> 이 문서는 전처리 파이프라인의 **실행·코드 SSOT**다 — `parse_laws.py`, `parse_emc_pdf.py`, `preprocess.py`, `ingest.py`, `workflow.py`의 동작과 실행 절차가 여기 있다. RAG·임베딩·희석 같은 **개념·배경**은 [data_pipeline.md](data_pipeline.md)를 본다.

## 전체 그림

raw 데이터는 손대지 않는다. 스크립트가 raw를 읽어 `processed/`를 매번 새로 만들고, `ingest.py`가 그걸 pgvector에 적재한다.

```
data/raw/law_api/*.json        parse_laws.py        data/processed/*.md      ingest.py
data/raw/law_api/*.pdf      →   parse_emc_pdf.py  →  (조문 + 품목)        →   pgvector
(불변, gitignore)              (파싱·청킹)           (재생성 가능, gitignore)   (kc_legal / kc_items)
```

핵심 설계는 **두 컬렉션 분리**다.

| 컬렉션 | 무엇 | 임베딩 대상 | cert_level |
|---|---|---|---|
| `kc_legal` | 법령 조문 (~650건) | 본문 전체 | 없음 |
| `kc_items` | 별표 품목 (~510건) | **품목명만** | **metadata 필드** |

법령 조문은 자유형 텍스트라 의미(맥락) 검색이 맞고, 별표 품목은 "이 제품이 무슨 인증등급인가"를 품목명으로 정밀 매칭한다. **인증등급(cert_level)은 본문에서 추론하지 않고 metadata에서 그대로 꺼낸다** — LLM이 긴 본문에서 등급을 잘못 읽는 오류를 구조적으로 없애기 위해서다. 자세한 근거는 [data_pipeline.md §2](data_pipeline.md)를 본다.

---

## 실행 절차

```bash
cd ai-service

# 1. raw 법령 JSON → processed/*.md (조문 + 분류별표 품목)
uv run python pipeline/parse_laws.py

# 2. EMC 별표1 PDF → processed/*.md (전자파 품목)
uv run python pipeline/parse_emc_pdf.py

# 3. processed/*.md → pgvector 적재 (kc_legal + kc_items)
uv run python pipeline/ingest.py
```

선행 조건:
- `docker-compose up -d`로 pgvector 컨테이너가 떠 있어야 한다.
- `.env`에 `GCP_PROJECT`가 있어야 한다(임베딩이 Vertex AI를 호출하므로). 인증은 GCP ADC — [ai-service/CLAUDE.md](../ai-service/CLAUDE.md) 참조.

`ingest.py`는 실행마다 컬렉션을 지우고 다시 넣는다(idempotent). Vertex 임베딩은 요청당 250건 제한이라 200건씩 끊어 보낸다.

---

## 각 단계가 하는 일

### parse_laws.py — 법령 JSON → 조문·품목 .md

- **조문**: 조문 1개 = 파일 1개. JSON이 이미 조문 단위로 끊어 주므로 `law_name`/`article`/`effective_date`를 응답에서 자동으로 뽑아 frontmatter를 채운다.
- **분류 별표**: 품목 1개 = 파일 1개로 쪼갠다. 통째로 임베딩하면 수십 개 품목이 섞여 검색이 희석되기 때문이다([data_pipeline.md §1-4](data_pipeline.md)).
  - 대상은 `CLASSIFICATION_APPENDICES`에 박힌 7개 별표뿐이다(안전 별표3~6, 어린이 별표1~3). 나머지 별표(서식·과태료·행정처분 등)는 검색 가치가 없고 ASCII 박스 노이즈만 더해 **전부 제외**한다.
  - 품목별로 **실제 category를 재지정**한다(섹션 헤더로 판별). 안전 별표3은 전기용품과 생활용품을 한 파일에 담고 있어, 품목마다 제대로 갈라 태깅해야 카테고리 필터가 정확하다.
- **행정규칙**(EMC 고시)은 조문만 처리한다. 별표1은 PDF로 따로 파싱한다(아래).

### parse_emc_pdf.py — EMC 별표1 PDF → 전자파 품목 .md

전자파 품목 분류표는 「방송통신기자재등의 적합성평가에 관한 고시」 별표1에만 있다. 현행법령 API의 별표 JSON은 1,900줄 넘는 복잡한 ASCII 표라 파싱이 비현실적이라, 같은 별표를 PDF로 받아 `pdfplumber`로 칸을 추출한다.

- 페이지마다 헤더 컬럼 구성이 달라(12열/8열) 컬럼 인덱스를 고정하지 않고 헤더 키워드로 동적 매핑한다.
- 기기부호(HDR11 등)가 있는 행 = 품목 1건. `적합인증/적합등록/자기적합확인` 컬럼의 ○ 위치로 cert_level을 자동 판정한다.

### preprocess.py — 본문 정제 (공용 유틸)

`clean_legal_text()`가 임베딩 직전 본문에서 노이즈를 제거한다. parse 스크립트와 `ingest.py` 양쪽이 호출한다.

- `<개정 …>`·`<신설 …>` 등 인라인 마커 제거
- `1) 삭제 <…>` 같은 삭제 항목 줄 통째 제거(폐지된 규정이 검색되지 않도록)
- 가운뎃점 변종(`ㆍ`·`‧`·PDF 추출 오류 `ž`) → `·` 통일, 전각 공백 정리, NFC 정규화

`normalize_inline()`은 frontmatter 값·표 셀처럼 짧은 문자열용(개행 제거 + 양끝 정리)이다.

### ingest.py — 두 컬렉션으로 분리 적재

`processed/*.md`를 읽어 frontmatter의 **`item_name` 유무**로 가른다: 있으면 품목(kc_items, 품목명만 임베딩 + 본문은 metadata에 보관), 없으면 조문(kc_legal, 본문 전체 임베딩).

---

## frontmatter 필드

parse 스크립트가 자동으로 채운다. 수동 작성이 아니다.

| 필드 | 의미 | 예시 |
|---|---|---|
| `doc_type` | 문서 종류 | 법률 / 시행령 / 시행규칙 / 별표 / 고시 |
| `axis` | 인증 축 | 안전 / 전자파 |
| `category` | 제품 카테고리 (필터 기준) | 전기용품 / 생활용품 / 어린이제품 |
| `cert_level` | 인증 등급 (품목 전용) | 안전인증 / 안전확인 / 공급자적합성확인 / 적합등록 … |
| `item_name` | 품목명 (품목 전용, 컬렉션 분기 기준) | 모발관리기 |
| `law_name` | 법령명 | 전기용품 및 생활용품 안전관리법 |
| `article` | 조항/별표 위치 | 제5조(안전인증 등) / 별표3 (…) |
| `effective_date` | 시행일 | 2026-04-01 |
| `source_url` | 원문 URL | https://… |

---

## 워크플로우에서 어떻게 쓰이나

`workflow.py`는 두 컬렉션을 각각 검색한다([data_pipeline.md §0](data_pipeline.md)의 사용 단계).

- **retrieve_node** → `kc_legal`을 **법령 검색 질의**로 검색(인증의 이유·절차·시험항목 근거).
- **match_items_node** → `kc_items`를 **제품 정체성 질의**(제품명+용도+사양)로 검색. 법령 질의를 그대로 쓰면 엉뚱한 품목이 잡혀 분리했다.
- 두 검색 모두 `category` 필터를 쓴다. **축(안전/전자파)이 아니라 category로** 거른다 — 축으로 거르면 "안전+전자파 동시 인증"을 한 번에 못 잡아 핵심 기능이 깨진다. 전기용품 질의는 안전 조문의 결합 카테고리(`전기용품,생활용품`)도 함께 매칭되도록 확장한다. 0건이면 필터를 풀고 재검색한다.
- **diagnose_node** → 품목 매칭의 cert_level을 권위 있는 값으로 받고, 법령 본문으로 등급을 새로 추론하지 않는다.
- **신뢰도**: 분류표에 등재된 인증은 최소 MEDIUM을 보장하고 충실성(llm_score)이 그 위로 끌어올린다. 같은 축에서 등급이 다른 품목이 매칭 마진(`ITEM_AMBIGUITY_MARGIN`) 이내로 붙으면 등급이 모호한 것으로 보고 `needs_expert_review`를 세운다.

---

## 검증

적재 후 검색이 의도대로 되는지 직접 확인한다.

```bash
cd ai-service
uv run python -c "
from llm import get_vector_store, cosine_distance_to_similarity
import settings
store = get_vector_store(settings.ITEM_COLLECTION)
for doc, dist in store.similarity_search_with_score('헤어드라이어 가정용 모발 건조', k=8):
    m = doc.metadata
    print(round(cosine_distance_to_similarity(dist), 3), '|', m.get('axis'), m.get('cert_level'), '|', m.get('item_name'))
"
```

확인 포인트:
- 안전 품목(모발관리기·가정용 미용기기)과 전자파 품목(전기건조기류·이·미용기기류)이 **둘 다** 상위에 나오는가 → 안전+전자파 동시 식별의 토대.
- 품목이 통짜가 아니라 품목당 1건으로 들어갔는가.
- 전체 진단은 `from workflow import run_assessment`로 돌려 `matched_item`·`confidence`·`needs_expert_review`를 본다.

> 실측 주의: "헤어드라이어"는 안전축에서 가정용 미용기기(안전확인)와 모발관리기(안전인증)가 근소한 차이로 붙는다. 모호성 플래그가 이 경우를 잡아 전문가 검토를 권한다 — 단정해서 틀리는 것보다 낫다.

---

## 신규 데이터 추가 절차

raw에 데이터를 넣고 스크립트를 다시 돌리면 끝이다. 수동 .md 작성·분할은 없다.

1. `fetch_laws.py`로 raw에 법령/고시를 받는다(또는 PDF를 `data/raw/`에 둔다).
2. 새 법령이면 `parse_laws.py`의 `SLUG_META`(축/카테고리/문서종류)에 항목을 추가한다. 분류 별표면 `CLASSIFICATION_APPENDICES`에 `(slug, 별표번호) → cert_level/mode`를 등록한다.
3. `parse_laws.py` → `parse_emc_pdf.py` → `ingest.py` 순서로 재실행한다.
4. 위 검증 스니펫으로 확인한다.

---

## 에러 레퍼런스

| 증상 | 원인 | 해결 |
|---|---|---|
| `GCP_PROJECT가 설정되지 않았습니다` | `.env`에 프로젝트 없음 | `ai-service/.env`에 `GCP_PROJECT=<ID>` |
| `expected 768 dimensions, not 3072` | 임베딩 컬럼이 옛 차원으로 고정됨 | langchain 테이블 드롭 후 재적재 ([ai-service/CLAUDE.md](../ai-service/CLAUDE.md) 임베딩 차원 변경) |
| `batchSize … supported range is … 251` | Vertex 임베딩 250건 초과 | `ingest.py`가 200건씩 배치(이미 처리됨). 직접 호출 시 250 미만으로 |
| ingest 시 DB 연결 실패 | pgvector 미기동 | `docker-compose up -d` |
| 무관한 품목이 매칭됨 | category 태깅 누락 / 질의 오염 | parse의 category 재지정 확인. 품목 매칭은 제품 질의를 쓰는지 확인 |
