# CLAUDE.md (frontend)

이 파일은 `frontend/` 디렉토리에서 작업할 때 적용되는 추가 가이드다. 프로젝트 전체 컨텍스트는 루트 `CLAUDE.md` 참조.

## 스택

- **Next.js 15.5** (App Router) + **React 19.2**
- **TypeScript** strict 모드
- **Tailwind CSS 3.4**
- **Jest 30** + `@testing-library/react` + `jsdom` 환경 (`next/jest` 프리셋)
- **ESLint**: `next/core-web-vitals` + `next/typescript`

## 디렉토리 규칙

App Router 구조다. 모든 코드는 `src/app/` 아래에 배치한다.

```
src/
├── app/
│   ├── layout.tsx          # 루트 레이아웃
│   ├── page.tsx            # 루트 페이지 (/)
│   ├── globals.css         # 전역 스타일
│   └── fonts/              # Geist 폰트 파일
```

## TypeScript 경로 별칭

`@/*` → `./src/*` 로 매핑돼 있다. 임포트는 항상 별칭 사용:

```ts
import { Foo } from '@/components/Foo'   // ✓
import { Foo } from '../../components/Foo' // ✗
```

## 개발 명령어

```bash
npm run dev                              # 개발 서버 (포트 3000)
npm run build                            # 프로덕션 빌드 (CI에서 실행)
npm run lint                             # ESLint
npm test                                 # Jest 전체
npm test -- src/app/foo.test.tsx         # 단일 파일
npm test -- -t "패턴"                    # 테스트명 패턴 매칭
```

## App Router 작업 시 주의사항

- `page.tsx` / `layout.tsx` / `loading.tsx` / `error.tsx` 등 **파일명이 곧 라우팅 규약**이다. 임의 명명 금지.
- 기본은 Server Component. 브라우저 API/`useState`/`useEffect` 필요한 경우만 파일 최상단에 `'use client'` 명시.
- Server Component에서 `fetch` 호출 시 Next.js가 자동 캐싱한다. 캐싱 비활성화는 `{ cache: 'no-store' }` 옵션 사용.

## Backend 연동

backend는 `http://localhost:8080`에서 동작하며, Spring Security가 모든 엔드포인트에 기본 인증을 요구한다 (`application.yaml`의 `admin`/`admin`). API 호출 시 인증 처리 필요. CORS 설정도 backend 측에서 확인할 것.

## 테스트 작성

- 환경: `jsdom` (브라우저 API 시뮬레이션)
- `@testing-library/jest-dom` 매처 사용 가능 (`toBeInTheDocument` 등)
- 파일명: `*.test.tsx` 또는 `*.test.ts`
- 테스트 파일 위치는 컨벤션 미정 — 컴포넌트 옆에 두는 방식 권장

## 현재 상태

App Router 초기 스캐폴드만 있는 상태 (`page.tsx`는 Next.js 기본 템플릿). 실제 비즈니스 페이지는 아직 구현 전.
