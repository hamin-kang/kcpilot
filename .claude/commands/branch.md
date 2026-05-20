다음 단계를 순서대로 실행해줘.

**1단계: 작업 정보 수집**

아래 내용을 사용자에게 질문해줘 (한 번에 모아서):

1. 작업 유형 선택:
   | 번호 | 타입 | 설명 | 분기 기준 |
   |------|------|------|-----------|
   | 1 | feat | 새로운 기능 개발 | develop |
   | 2 | bugfix | develop 내 버그 수정 | develop |
   | 3 | hotfix | 운영 서버(main) 긴급 버그 수정 | main |
   | 4 | refactor | 코드 구조 개선 | develop |
   | 5 | chore | 빌드 설정, 의존성 추가 | develop |
   | 6 | docs | 문서 작성 및 수정 | develop |

2. 작업 내용을 간단히 설명하는 영문 subject (예: payment, login-error, db-optimization)
3. 연결된 GitHub 이슈 번호 (없으면 없다고 해도 됨)

**2단계: 브랜치명 제안**

kcpilot 브랜치 컨벤션에 맞게 브랜치명을 만들어줘.

**형식:** `type/subject-#이슈번호`

- subject는 소문자 영문과 하이픈(`-`)만 사용
- 이슈 번호가 없으면 `#이슈번호` 부분 생략
- 예시: `feat/payment-#12`, `bugfix/login-error-#21`, `hotfix/payment-null-#45`

제안한 브랜치명을 코드 블록으로 보여줘.

**3단계: 브랜치 생성 실행**

"위 브랜치를 생성하고 이동할까요?" 라고 물어봐줘.
사용자가 승인하면 아래를 순서대로 실행해줘:

1. 기준 브랜치(develop 또는 main)로 이동: `git checkout develop` (hotfix면 `git checkout main`)
2. 최신 상태로 업데이트: `git pull origin develop` (hotfix면 `git pull origin main`)
3. 새 브랜치 생성 및 이동: `git checkout -b 브랜치명`
4. 완료 후 현재 브랜치 확인: `git branch --show-current`
