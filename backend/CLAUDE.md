# CLAUDE.md (backend)

이 파일은 `backend/` 디렉토리에서 작업할 때 적용되는 추가 가이드다. 프로젝트 전체 컨텍스트는 루트 `CLAUDE.md` 참조.

## 스택

- **Spring Boot 3.5** + **Java 21** (toolchain으로 강제)
- **Gradle Kotlin DSL** (`build.gradle.kts`)
- **JPA + Hibernate** (PostgreSQL dialect)
- **PostgreSQL 18** + **pgvector 0.8.2** (벡터 검색은 ai-service에서 주도, backend는 RDBMS 접근만 담당)
- **Spring Security**
- **Spring Validation**
- **Lombok** (annotation processor)
- **springdoc-openapi** 2.8 → Swagger UI 자동 생성

## 패키지 구조

- 루트 패키지: `com.kcpilot`
- 진입점: `src/main/java/com/kcpilot/BackendApplication.java`
- 설정 파일: `src/main/resources/application.yaml`
- 테스트: `src/test/java/com/kcpilot/`

현재는 진입점 클래스 하나뿐인 초기 상태. 패키지 구조는 도메인별 분리(예: `com.kcpilot.assessment`, `com.kcpilot.user`)를 기본 가정으로 한다.

## 사전 조건

backend 실행 전 **PostgreSQL이 떠 있어야 한다**. 루트에서 `docker-compose up -d` 먼저 실행 (pgvector 확장은 init 스크립트로 자동 활성화됨).

`application.yaml`의 datasource 자격증명(`hamin`/`1234`, 포트 5432)은 `docker-compose.yaml`의 환경변수와 일치해야 한다. 둘 중 하나라도 바꾸면 같이 수정할 것.

## 개발 명령어

```bash
./gradlew bootRun                                    # 개발 서버 (포트 8080)
./gradlew build                                      # 빌드 + 테스트 (CI에서 실행)
./gradlew test                                       # 전체 테스트
./gradlew test --tests "BackendApplicationTests"     # 단일 테스트 클래스
./gradlew test --tests "*.someMethod"                # 단일 테스트 메서드
./gradlew test --info                                # 테스트 로그 상세 출력
./gradlew clean                                      # 빌드 산출물 정리
./gradlew dependencies                               # 의존성 트리 확인
```

## JPA / DB 작업 시 주의사항

- `ddl-auto: update` 설정이라 **엔티티 변경 → 서버 재시작 시 자동으로 스키마 반영**된다. 컬럼 추가는 자동, 삭제·이름 변경은 수동 처리 필요.
- `show-sql: true`, `format_sql: true`, `org.hibernate.SQL: DEBUG` 설정이라 실행되는 SQL이 콘솔에 출력된다 — 디버깅에 활용.
- 프로덕션에서는 `ddl-auto: validate` 또는 Flyway/Liquibase 마이그레이션 도구로 전환해야 한다.

## Spring Security 기본 인증

`application.yaml`에 `spring.security.user.name=admin`, `password=admin`이 설정돼 있다. **모든 엔드포인트가 기본 폼 로그인을 요구**한다.

API 서버 용도라 이 기본 설정은 프로토타입 단계의 임시 상태다. 실제 인증 설계(JWT/OAuth 등) 시 `SecurityFilterChain` Bean을 정의해 교체해야 한다.

## Lombok 사용

`@Getter`, `@Setter`, `@Builder`, `@RequiredArgsConstructor` 등 자유롭게 사용 가능. IDE에서 Lombok plugin + annotation processing 활성화가 안 돼 있으면 컴파일은 되는데 IDE에서만 빨간 줄이 뜬다.

## OpenAPI / Swagger

`springdoc-openapi` 의존성 덕에 별도 설정 없이 다음 URL이 자동 노출된다:

- Swagger UI: `http://localhost:8080/swagger-ui.html`
- OpenAPI JSON: `http://localhost:8080/v3/api-docs`

Spring Security 때문에 접근 시 admin 로그인이 필요할 수 있다.

## 무시해도 되는 파일

- `HELP.md` — Spring Initializr가 자동 생성한 외부 링크 모음. 실제 가이드 가치 없음.
- `backend.iml`, `.idea/` — IntelliJ 메타데이터.
- `build/` — Gradle 산출물.
