# Git Convention & Branch Strategy

## Git Convention

### 1. 커밋 메시지 규칙

> 커밋 메시지는 작업 성격을 파악하기 위해 아래 형식을 지킨다.
> 

**구조:** `type: subject`

subject 규칙

- 마침표`.` 사용 금지
- 과거형이 아닌 현재형/명령조 사용 (예: 수정했음(X) -> 수정(O), Fix(O))

| 타입 (Type) | 설명 |
| --- | --- |
| **feat** | 새로운 기능 추가 |
| **fix** | 버그 수정 |
| **docs** | 문서 수정 (README 등) |
| **style** | 코드 포맷팅, 세미콜론 누락 수정 (로직 변경 없음) |
| **refactor** | 코드 리팩토링 |
| **test** | 테스트 코드 추가 및 수정 |
| **chore** | 빌드 업무, 패키지 매니저 설정 수정 |

### 2. 브랜치 명명 규칙

브랜치는 작업 종류와 이슈 번호를 조합하여 이름을 짓는다.

**형식:** `type/subject-#issue_number`

- **feat**: 기능 개발 시 사용 (예: `feat/payment-#12`)
- **bugfix**: develop 브랜치 내 버그 수정 시 사용 (예: `bugfix/login-error-#21`)
- **hotfix**: 운영 서버(main) 긴급 버그 수정 시 사용 (예: `hotfix/payment-null-#45`)
- **refactor**: 코드 구조 개선 시 사용 (예: `refactor/db-optimization-#33`)

---

## Branch Strategy

### 1. Main Branch (메인 브랜치)

#### 항상 유지되는 핵심 브랜치

- main: 라이브 서버에 실제 배포되는 브랜치. 배포 가능한 상태만을 관리하며 직접적인 커밋은 금지.
- develop: 다음 출시 버전을 준비하는 개발 브랜치. 기능 구현이 완료된 코드들이 모이는 통합 브랜치이다.

### 2. Supporting Branch (보조 브랜치)

#### 특정 작업을 위해 생성하고 목적 달성 후 삭제하는 브랜치

| 브랜치 종류 | 분기 지점 | 병합 대상 | 설명 |
| --- | --- | --- | --- |
| **feat** | `develop` | `develop` | 새로운 기능을 구현할 때 사용 |
| **release** | `develop` | `main`, `develop` | 출시 전 QA, 테스트, 버전 태깅 진행 |
| **hotfix** | `main` | `main`, `develop` | 운영 중인 서버(`main`)의 긴급 버그 수정 |
| **refactor** | `develop` | `develop` | 기능 변경 없는 코드 구조 및 로직 개선 |
| **bugfix** | `develop` | `develop` | `develop` 브랜치 내에서 발견된 버그 수정 |
| **chore** | `develop` | `develop` | 빌드 설정, 의존성 추가, 패키지 매니저 설정 변경 |
| **docs** | `develop` | `develop` | README, API 명세서 등 문서 작성 및 수정 |

### 3. 버전 관리 및 태깅 (Tagging)

배포 시점의 상태를 보존하고 특정 시점으로의 복구(Rollback)를 용이하게 하기 위해 main 브랜치 병합 시 태그를 생성한다.

태깅 규칙: Semantic Versioning (SemVer)
버전 번호는 vMajor.Minor.Patch 형식을 따른다.

`v1.0.0 (Major.Minor.Patch) Major: 대규모 개편 / Minor: 기능 추가 / Patch: 버그 수정`

| 버전 | 올리는 시점 | 예시 |
| --- | --- | --- |
| **Major** | 기존 사용자 경험 또는 연동 방식이 근본적으로 바뀔 때 | 로그인 방식 전면 교체, DB 스키마 대규모 변경으로 데이터 마이그레이션 필요, API 요청/응답 구조 변경 |
| **Minor** | 기존 기능을 깨지 않으면서 새로운 기능이 추가될 때 | 새 페이지 추가, 새 API 엔드포인트 추가, 새 외부 서비스 연동 |
| **Patch** | 기능 변화 없이 결함 수정이나 사소한 개선이 있을 때 | 버그 수정, 오타 수정, 성능 개선, 로그 추가 |

> **판단이 애매할 때 기준:** "기존에 잘 되던 기능이 이 변경으로 인해 사용자에게 다르게 동작하는가?" → Yes이면 Minor 이상, No이면 Patch.

### 4. 병합 정책 (Merge Policy)

브랜치를 합칠 때는 작업의 성격에 따라 두 가지 방식을 구분하여 사용한다.

| 상황 | 병합 방식 | 대상 브랜치 | 목적 |
| --- | --- | --- | --- |
| **개발 진행** | **Squash and Merge** | `feat, bugfix, refactor ...` → `develop` | 자잘한 커밋을 하나로 합쳐 히스토리 정돈 |
| **제품 배포** | **Merge Commit** | `release, hotfix` → `main` | 배포 시점의 명확한 기록 및 시각화 |

### 1) Squash and Merge (작업 이력 단일화)

`feat, bugfix, refactor ...` 보조 브랜치에서 작업할 때 발생하는 수많은 ‘자잘한’ 커밋들을 하나로 뭉쳐서 `develop`에 합치는 방식이다.

- **왜 하는가?:**
개발하다 보면 “오타 수정”, “중간 저장”, “테스트 실패 수정” 같은 의미 없는 커밋이 쌓인다.
이걸 그대로 합치면 나중에 `develop` 히스토리를 볼 때 실제 핵심 기능을 찾기가 너무 힘들어질 수 있다.
- **예시**
    - **작업 중 커밋들:**
        1. `feat: 결제 엔티티 설계`
        2. `feat: 오타 수정`
        3. `feat: 테스트 코드 작성`
        4. `fix: 테스트 통과하게 수정`
- **병합 후 (develop 브랜치):**
    - `feat: 결제 시스템 구현 및 검증 (#12)` (커밋 1개가 됨)
- Squash and Merge를 실행할 때, 기본적으로 PR 제목이 최종 커밋 메시지가 된다.
    - PR 제목: 커밋 메시지 규칙과 동일하게 하되, 끝에 이슈 번호를 붙인다.

### 2) Merge Commit (배포 기록 생성)

- 대상: release, hotfix 브랜치 → main 브랜치 병합 시
- 목적: main 브랜치의 히스토리에서 배포 시점(출시 버전)을 시각적으로 명확히 분리하고 기록하기 위함이다.
- 두 브랜치가 만나는 지점에 ’병합 커밋’이라는 새로운 점을 하나 찍는 방식이다.
    - 동작 및 절차:
        1. GitHub PR 페이지에서 [Create a merge commit] 옵션을 선택하여 병합한다.
        2. 병합 완료 후 생성된 Merge Commit 지점에 해당 버전의 태그(예: v1.0.0)를 부착한다.
        3. 태그 생성은 GitHub의 Releases 기능을 사용하거나 Git CLI를 통해 수동으로 진행한다.
        4. 배포가 완료되면 해당 변경사항을 develop 브랜치에 역병합(Back-merge)하여 소스 코드를 동기화한다.

### 3) Squash Merge 단위 원칙

Squash Merge의 효과는 **"PR 1개 = 의미 있는 작업 1개"** 가 지켜질 때 극대화된다.
의미 있는 중간 단계가 여러 개인 대형 작업(예: 스키마 설계 → 레포지토리 구현 → 서비스 레이어 구현)은
하나의 PR로 묶지 말고 **작업 단위로 PR을 분리**하여 각각 Squash한다.

---

### 5. 핵심 운영 규칙 (Branch Protection & CI Policy)

#### 브랜치 보호 규칙 (GitHub Branch Protection Rules)

| 브랜치 | 직접 push | 병합 조건 |
| --- | --- | --- |
| `main` | **금지** | PR + CI 통과 필수 |
| `develop` | **금지** | PR + CI 통과 필수 |

> GitHub 저장소 Settings → Branches → Branch protection rules 에서 설정한다.
> - `Require a pull request before merging` 활성화
> - `Require status checks to pass` 체크하면 아래 "No required checks"에 GitHub Actions 워크플로우 이름을 추가해야 함.

#### CI 통과 조건 (병합 전 필수 확인)

PR을 `develop` 또는 `main`에 병합하기 전, 아래 항목이 모두 통과되어야 한다.

- [ ] 빌드 성공 (`./gradlew build`)
- [ ] 전체 테스트 통과 (`./gradlew test`)

#### 브랜치 삭제 정책

- PR 병합 완료 후 해당 보조 브랜치는 **즉시 삭제**한다.
- GitHub의 `Automatically delete head branches` 옵션을 활성화하여 자동 삭제를 권장한다.
- `release`, `hotfix` 브랜치는 태그 부착 및 back-merge 완료 후 삭제한다.

---

### 4) Conflict(충돌) 관리

- 충돌 해결 규칙:
    - 보조 브랜치를 develop에 합치기 전, 반드시 develop의 최신 내용을 자신의 브랜치로 가져와(Pull/Merge)
    충돌 여부를 확인하고 로컬에서 먼저 해결한 뒤 PR을 요청한다.