# CLAUDE.md (ai-service)

이 파일은 `ai-service/` 디렉토리에서 작업할 때 적용되는 추가 가이드다. 프로젝트 전체 컨텍스트는 루트 `CLAUDE.md` 참조.

## 스택

- **FastAPI** + **Uvicorn**
- **Python 3.11** (`.python-version` 명시, uv 관리)
- **LangChain** / **LangGraph** / **langchain-google-genai** (Google Gemini)
- **Gemini** — chat(gemini-2.5-flash) + embeddings(gemini-embedding-001, 768차원)
- **PDF 처리**: pdfminer.six, pdfplumber, pypdfium2, pillow
- **벡터 검색**: PostgreSQL + **pgvector** (LangChain의 `langchain-postgres` PGVector 래퍼 사용, DB 접속은 `psycopg[binary]`)
- **토큰 계산**: tiktoken
- **pytest** (테스트, dev 의존성)

벡터 저장소는 backend가 쓰는 PostgreSQL과 **동일 인스턴스를 공유**한다 (포트 5432, DB `kcpilot`). 컨테이너는 루트 `docker-compose.yaml`로 띄운다.

## 패키지 관리 (uv)

이 프로젝트는 **uv**로 관리된다. `pyproject.toml`에 의존성 정의, `uv.lock`으로 버전 고정.

```bash
# 처음 클론 후 환경 세팅 (한 번만)
uv sync                          # .venv 생성 + 의존성 설치 (dev 포함)
uv sync --no-dev                 # dev 의존성 제외

# 패키지 추가/제거
uv add <package>                 # 프로덕션 의존성 추가
uv add --dev <package>           # 개발 의존성 추가
uv remove <package>              # 패키지 제거
```

`uv.lock`은 git에 커밋한다 (package-lock.json과 같은 역할).  
`.venv/`는 gitignore 처리 — `uv sync`로 언제든 재생성 가능.

**로컬은 `uv sync`** (lock 자동 갱신 허용), **CI는 `uv sync --locked`** — lock이 `pyproject.toml`과 어긋나면 빌드를 실패시켜 stale lock을 잡는다. CI에서 `--frozen`이나 uv 버전 정확 핀은 쓰지 않는다: 재현성은 `uv.lock`이 담당하고, 버전 핀은 자동 갱신 봇(Renovate/Dependabot) 없이는 부채가 되기 때문.

## 환경변수 (.env)

`main.py`가 `load_dotenv()`를 호출해 `.env`에서 환경변수를 읽는다. Gemini 호출에는 `GOOGLE_API_KEY`, pgvector 접속에는 `DATABASE_URL`이 필요하다.

```env
GOOGLE_API_KEY=...
DATABASE_URL=postgresql+psycopg://hamin:1234@localhost:5432/kcpilot
```

`.env`는 절대 커밋하지 말 것 (`.gitignore` 처리됨).

## 개발 명령어

```bash
uv run uvicorn main:app --reload                       # 개발 서버 (포트 8000)
uv run uvicorn main:app --host 0.0.0.0 --port 8000    # 외부 접속 허용

uv run pytest                                          # 전체 테스트
uv run pytest tests/test_smoke.py                      # 단일 파일
uv run pytest tests/test_smoke.py::test_name           # 단일 테스트 함수
uv run pytest -v                                       # 상세 출력
uv run pytest -k "패턴"                                # 이름 패턴 매칭
```

## 데이터 파이프라인 명령어

```bash
uv run python pipeline/fetch_laws.py    # 국가법령정보 API → data/raw/law_api/ 저장
uv run python pipeline/ingest.py        # data/legal/*.md → pgvector 적재
```

`uv run`은 `.venv`를 자동으로 인식하므로 `source .venv/bin/activate` 불필요.  
직접 활성화하고 싶다면: `source .venv/bin/activate`

## 자동 생성 문서

FastAPI는 OpenAPI 문서를 자동 노출한다:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 현재 엔드포인트

```
GET  /ai/health           → {"status": "ok", "service": "ai-service"}  (정상 동작)
POST /ai/run-assessment   → AssessmentResult (LangGraph 워크플로우 실행)
```

`/ai/run-assessment`는 `schemas.AssessmentRequest`를 받아 LangGraph 워크플로우(`workflow.py`)를 실행하고 `AssessmentResult`를 반환한다.

## 백엔드 연동

`backend` (Spring Boot)가 ai-service의 `/ai/run-assessment`를 호출하는 구조다. 엔드포인트 경로/요청 스키마 변경 시 backend 측 클라이언트 코드도 함께 수정해야 한다.

## 테스트

- 현재 `tests/test_smoke.py` 하나만 존재 (스모크 테스트).
- 새 테스트 추가 시 `tests/test_*.py` 규칙 사용 — pytest가 자동 수집한다.
- LangChain/LangGraph 호출이 들어가는 테스트는 OpenAI API를 실제로 호출하지 않도록 mock 처리 또는 fake LLM 사용 권장.

## 패키지 구조

현재 `main.py` 단일 파일 상태. 코드가 늘어나면 다음 구조 권장:

```
ai-service/
├── main.py              # FastAPI 앱 + 라우터 등록
├── routers/             # 엔드포인트 모듈
├── workflows/           # LangGraph 워크플로우
├── chains/              # LangChain 체인
├── schemas/             # Pydantic 모델
└── tests/
```
