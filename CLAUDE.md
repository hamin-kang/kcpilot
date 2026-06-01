# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

KCpilot은 KC 인증 사전진단 AI 서비스로, 3개 서비스로 구성된 모노레포다.

- **backend/** — Spring Boot 3.5 (Java 21), PostgreSQL, JPA, Spring Security, springdoc-openapi
- **frontend/** — Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Jest
- **ai-service/** — FastAPI, Python 3.11, LangChain/LangGraph, OpenAI, pgvector

## 서비스 간 관계

- `frontend` (Next.js) → `backend` (Spring Boot, 8080) → PostgreSQL
- `backend` → `ai-service` (FastAPI): KC 인증 사전진단 워크플로우 실행 위임
- `ai-service` → PostgreSQL (pgvector): RAG용 임베딩·법령 텍스트 검색 (관계형 DB와 동일 인스턴스 공유)
- `ai-service`는 LangGraph 기반 워크플로우 (`main.py`의 `/ai/run-assessment` 엔드포인트, 아직 미구현)

## 인프라

PostgreSQL(pgvector 확장 포함)은 docker-compose로 띄운다. backend·ai-service 실행 전 필수.

```bash
docker-compose up -d        # PostgreSQL 18 + pgvector 0.8.2 (포트 5432, DB: kcpilot)
docker-compose down
```

이미지는 `pgvector/pgvector:0.8.2-pg18`을 사용한다 (PG·pgvector 둘 다 핀 박음). `infra/postgres/init/01-init.sql`이 컨테이너 첫 부팅 시 자동 실행되어 `CREATE EXTENSION vector`가 적용된다. (재실행이 필요하면 `docker-compose down -v`로 볼륨까지 제거 후 다시 `up -d`.)

`application.yaml`의 datasource 자격증명(`hamin`/`1234`)은 `docker-compose.yaml` 환경변수와 일치해야 한다.

## 명령어

- **설치·실행 전체** → [README.md](README.md)가 SSOT (사전 요구사항 · `.env` 설정 · 서비스 기동 순서)
- **서비스별 상세 명령 · 작업 규칙** → 각 디렉토리의 CLAUDE.md: [backend](backend/CLAUDE.md) · [frontend](frontend/CLAUDE.md) · [ai-service](ai-service/CLAUDE.md)

## Git 워크플로우

**모든 커밋/브랜치는 `docs/git_convention.md` 규칙을 따른다.** 이 파일에는 다음이 정의돼 있다:

- 커밋 메시지 형식: `type: subject` (feat/fix/docs/style/refactor/test/chore)
- 브랜치 명명: `type/subject-#issue_number` (예: `feat/payment-#12`)
- 브랜치 전략: `main` (배포), `develop` (통합). 보조 브랜치는 `develop`에서 분기 후 squash merge
- `hotfix`만 `main`에서 분기, `main` + `develop` 양쪽으로 merge commit
- `main`/`develop` 직접 push 금지, PR + CI 통과 필수

CI는 PR 시 backend(`./gradlew build`), frontend(`build`/`lint`/`test`), ai-service(`pytest`) 모두 실행한다 (`.github/workflows/ci.yaml`).

## 커스텀 슬래시 커맨드

- `/commit` — `git diff --staged` 분석 후 `docs/git_convention.md` 규칙에 맞춰 커밋 메시지 작성 (`.claude/commands/commit.md`)
- `/branch` — 작업 유형/subject/이슈 번호 입력받아 컨벤션 맞는 브랜치 생성 (`.claude/commands/branch.md`)

## 서브에이전트

- `security-reviewer` (`.claude/agents/security-reviewer.md`) — SQL/XSS/커맨드 인젝션, 인증·인가 결함, 시크릿 노출, 안전하지 않은 데이터 처리 검토. 스타일/성능은 다루지 않음.

## 주의사항

- `application.yaml`의 DB 비밀번호와 admin 자격증명은 개발용 하드코딩 상태다. 프로덕션 설정 시 환경변수로 분리 필요.
- backend의 JPA `ddl-auto: update`는 개발 편의용이며 프로덕션에서는 `validate` 또는 마이그레이션 도구로 전환해야 한다.
- ai-service의 LangGraph 워크플로우 연결(`/ai/run-assessment`)이 다음 핵심 작업이다.
