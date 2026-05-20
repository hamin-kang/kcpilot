# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

KCpilot은 KC 인증 사전진단 AI 서비스로, 3개 서비스로 구성된 모노레포다.

- **backend/** — Spring Boot 3.5.14 (Java 21), MySQL, JPA, Spring Security, springdoc-openapi
- **frontend/** — Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Jest
- **ai-service/** — FastAPI, Python 3.11, LangChain/LangGraph, OpenAI

## 서비스 간 관계

- `frontend` (Next.js) → `backend` (Spring Boot, 8080) → MySQL
- `backend` → `ai-service` (FastAPI): KC 인증 사전진단 워크플로우 실행 위임
- `ai-service`는 LangGraph 기반 워크플로우 (`main.py`의 `/ai/run-assessment` 엔드포인트, 아직 미구현)

## 인프라

MySQL은 docker-compose로 띄운다. backend 실행 전 필수.

```bash
docker-compose up -d        # MySQL 8.0 (포트 3306, DB: kcpilot)
docker-compose down
```

`application.yaml`의 datasource 자격증명(`hamin`/`1234`)은 `docker-compose.yml` 환경변수와 일치해야 한다.

## 자주 쓰는 명령어

### Backend (Spring Boot)

```bash
cd backend
./gradlew bootRun                              # 개발 서버 실행 (포트 8080)
./gradlew build                                # 빌드 + 테스트
./gradlew test                                 # 전체 테스트
./gradlew test --tests "BackendApplicationTests"  # 단일 테스트 클래스
./gradlew test --tests "*.someMethod"          # 단일 테스트 메서드
```

JPA는 `ddl-auto: update` 설정이라 엔티티 변경 시 자동으로 스키마 반영됨.

### Frontend (Next.js)

```bash
cd frontend
npm run dev                                    # 개발 서버
npm run build                                  # 프로덕션 빌드
npm run lint                                   # ESLint
npm test                                       # Jest 전체
npm test -- path/to/file.test.tsx              # 단일 테스트 파일
```

### AI Service (FastAPI)

```bash
cd ai-service
source .venv/bin/activate                      # 가상환경 활성화
pip install -r requirements.txt
uvicorn main:app --reload                      # 개발 서버 (기본 8000)
pytest                                         # 전체 테스트
pytest tests/test_xxx.py::test_func            # 단일 테스트
```

`.env` 파일에서 OpenAI 키 등을 로드한다 (`load_dotenv()`).

## Git 워크플로우

**모든 커밋/브랜치는 `docs/git_convention.md` 규칙을 따른다.** 이 파일에는 다음이 정의돼 있다:

- 커밋 메시지 형식: `type: subject` (feat/fix/docs/style/refactor/test/chore)
- 브랜치 명명: `type/subject-#issue_number` (예: `feat/payment-#12`)
- 브랜치 전략: `main` (배포), `develop` (통합). 보조 브랜치는 `develop`에서 분기 후 squash merge
- `hotfix`만 `main`에서 분기, `main` + `develop` 양쪽으로 merge commit
- `main`/`develop` 직접 push 금지, PR + CI 통과 필수

CI는 PR 시 backend(`./gradlew build`), frontend(`build`/`lint`/`test`), ai-service(`pytest`) 모두 실행한다 (`.github/workflows/ci.yml`).

## 커스텀 슬래시 커맨드

- `/commit` — `git diff --staged` 분석 후 `docs/git_convention.md` 규칙에 맞춰 커밋 메시지 작성 (`.claude/commands/commit.md`)
- `/branch` — 작업 유형/subject/이슈 번호 입력받아 컨벤션 맞는 브랜치 생성 (`.claude/commands/branch.md`)

## 서브에이전트

- `security-reviewer` (`.claude/agents/security-reviewer.md`) — SQL/XSS/커맨드 인젝션, 인증·인가 결함, 시크릿 노출, 안전하지 않은 데이터 처리 검토. 스타일/성능은 다루지 않음.

## 주의사항

- `application.yaml`의 DB 비밀번호와 admin 자격증명은 개발용 하드코딩 상태다. 프로덕션 설정 시 환경변수로 분리 필요.
- backend의 JPA `ddl-auto: update`는 개발 편의용이며 프로덕션에서는 `validate` 또는 마이그레이션 도구로 전환해야 한다.
- ai-service의 `/ai/run-assessment`는 현재 `not_implemented` 상태. LangGraph 워크플로우 연결이 다음 작업.
