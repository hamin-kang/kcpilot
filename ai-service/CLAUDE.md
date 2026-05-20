# CLAUDE.md (ai-service)

이 파일은 `ai-service/` 디렉토리에서 작업할 때 적용되는 추가 가이드다. 프로젝트 전체 컨텍스트는 루트 `CLAUDE.md` 참조.

## 스택

- **FastAPI 0.115** + **Uvicorn**
- **Python 3.11** (`.python-version` 명시)
- **LangChain 1.3** / **LangGraph 1.2** / **langchain-openai** 1.2
- **OpenAI** SDK 2.37
- **PDF 처리**: pdfminer.six, pdfplumber, pypdfium2, pillow
- **벡터 검색**: faiss-cpu
- **토큰 계산**: tiktoken
- **pytest** (테스트)

## 가상환경

`.venv/` 디렉토리에 가상환경이 이미 만들어져 있다. 활성화 후 작업:

```bash
source .venv/bin/activate                       # 활성화 (macOS/Linux)
pip install -r requirements.txt                 # 의존성 설치/동기화
deactivate                                      # 비활성화
```

새 패키지 추가 시:

```bash
pip install <package>
pip freeze > requirements.txt                   # requirements.txt 갱신
```

## 환경변수 (.env)

`main.py`가 `load_dotenv()`를 호출해 `.env`에서 환경변수를 읽는다. **현재 `.env` 파일은 비어 있다**. OpenAI 호출이 필요한 코드를 추가하려면 `OPENAI_API_KEY`를 먼저 설정해야 한다.

```env
OPENAI_API_KEY=sk-...
```

`.env`는 절대 커밋하지 말 것 (`.gitignore` 확인 필요).

## 개발 명령어

```bash
uvicorn main:app --reload                       # 개발 서버 (포트 8000, 자동 리로드)
uvicorn main:app --host 0.0.0.0 --port 8000     # 외부 접속 허용

pytest                                          # 전체 테스트
pytest --ignore=.venv                           # CI와 동일 (가상환경 제외)
pytest tests/test_smoke.py                      # 단일 파일
pytest tests/test_smoke.py::test_name           # 단일 테스트 함수
pytest -v                                       # 상세 출력
pytest -k "패턴"                                # 이름 패턴 매칭
```

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
