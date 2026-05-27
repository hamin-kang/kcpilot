# CLAUDE.md (ai-service)

이 파일은 `ai-service/` 디렉토리에서 작업할 때 적용되는 추가 가이드다. 프로젝트 전체 컨텍스트는 루트 `CLAUDE.md` 참조.

## 스택

- **FastAPI** + **Uvicorn**
- **Python 3.11** (`.python-version` 명시, uv 관리)
- **LangChain** / **LangGraph** / **langchain-openai**
- **OpenAI** SDK
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

## 환경변수 (.env)

`main.py`가 `load_dotenv()`를 호출해 `.env`에서 환경변수를 읽는다. **현재 `.env` 파일은 비어 있다**. OpenAI 호출이 필요한 코드를 추가하려면 `OPENAI_API_KEY`를, pgvector 접속에는 `DATABASE_URL`을 먼저 설정해야 한다.

```env
OPENAI_API_KEY=sk-...
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

`uv run`은 `.venv`를 자동으로 인식하므로 `source .venv/bin/activate` 불필요.  
직접 활성화하고 싶다면: `source .venv/bin/activate`

## 자동 생성 문서

FastAPI는 OpenAPI 문서를 자동 노출한다:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 현재 엔드포인트

```
GET  /ai/health           → {"status": "ok", "service": "ai-service"}  (정상 동작)
POST /ai/run-assessment   → {"status": "not_implemented"}              (미구현)
```

`/ai/run-assessment`는 LangGraph 워크플로우를 연결할 자리다. 현재는 `request: dict`를 받아 placeholder만 반환한다. 본격 구현 시 Pydantic 모델로 입출력 스키마를 정의해야 한다.

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
