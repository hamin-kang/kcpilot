# GCP 인프라 설정 가이드

로컬 터미널에서 `gcloud` CLI로 실행한다. 순서대로 따라가면 된다.

---

## 0. 사전 준비

**무엇**: gcloud CLI로 GCP에 로그인하고, 이번에 쓸 GCP 프로젝트를 지정한다.
그 다음 이번 배포에 필요한 GCP 서비스들을 활성화한다. GCP는 기능별로 API를 켜야 쓸 수 있다.

- `artifactregistry` — Docker 이미지 저장소
- `compute` — VM(서버) 생성
- `iamcredentials`, `iam` — GitHub Actions 인증 설정에 필요

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com
```

---

## 1. Artifact Registry 생성

**무엇**: Docker 이미지를 저장하는 저장소를 GCP 안에 만든다.
GitHub Actions가 빌드한 이미지를 여기에 올리고, VM이 여기서 내려받는다.
`asia-northeast3`는 서울 리전이다.

```bash
gcloud artifacts repositories create kcpilot \
  --repository-format=docker \
  --location=asia-northeast3 \
  --description="KCpilot container images"
```

---

## 2. Compute Engine VM 생성

**무엇**: 실제로 서비스가 돌아갈 서버(VM)를 만든다.

- `e2-standard-2` — 2 vCPU, 8GB RAM. Spring Boot JVM + FastAPI + Next.js + PostgreSQL 4개 서비스를 여유 있게 올릴 수 있는 최소 스펙.
- `ubuntu-2404-lts-amd64` — Ubuntu 24.04 LTS. 안정적인 리눅스 배포판.
- `--boot-disk-size=30GB` — 기본 10GB는 Docker 이미지 쌓이면 금방 찬다.
- `--scopes=cloud-platform` — 이게 핵심. VM 자체에 GCP 전체 접근 권한을 준다. 덕분에 ai-service가 Vertex AI를 호출할 때 별도 API 키 없이 VM 서비스 계정으로 자동 인증된다.
- `--tags=http-server` — 아래 방화벽 규칙을 이 VM에 적용하기 위한 태그.

```bash
gcloud compute instances create kcpilot-vm \
  --zone=asia-northeast3-a \
  --machine-type=e2-standard-2 \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=http-server,https-server \
  --scopes=cloud-platform
```

**무엇**: 외부에서 각 서비스 포트로 접근할 수 있도록 방화벽을 연다.
GCP는 기본적으로 22(SSH) 외엔 다 막혀 있다.

```bash
gcloud compute firewall-rules create allow-http \
  --allow=tcp:80,tcp:8080,tcp:8000,tcp:3000 \
  --target-tags=http-server
```

---

## 3. VM에 Docker 설치

**무엇**: VM에 SSH로 접속한 뒤 Docker를 설치한다.
이후 Step 4~7은 모두 VM 내부에서 실행한다.

```bash
# 로컬에서: VM에 SSH 접속
gcloud compute ssh kcpilot-vm --zone=asia-northeast3-a
```

```bash
# VM 내부에서
curl -fsSL https://get.docker.com | sh   # Docker 공식 설치 스크립트
sudo usermod -aG docker $USER            # sudo 없이 docker 명령어 쓸 수 있게
newgrp docker                            # 그룹 변경을 현재 세션에 바로 적용

docker compose version                   # 잘 설치됐는지 확인
```

---

## 4. VM에 소스 클론 및 환경변수 설정

**무엇**: VM에 소스코드를 내려받고, 프로덕션 환경변수 파일을 만든다.
`docker-compose.prod.yaml`이 `~/kcpilot` 경로를 기준으로 실행된다.

```bash
# VM 내부에서
git clone https://github.com/hamin-kang/kcpilot.git ~/kcpilot
cd ~/kcpilot

cp .env.prod.example .env.prod
vi .env.prod   # DB 비밀번호, 도메인 등 실제 값으로 채운다
```

---

## 5. Workload Identity Federation 설정

**무엇**: GitHub Actions가 GCP에 이미지를 올릴 때 인증이 필요하다.
보통은 서비스 계정 JSON 키를 GitHub에 저장하는데, 이 방식은 키가 유출되면 큰일이다.
Workload Identity는 "GitHub Actions에서 온 요청이 맞으면 인증해줘"라는 신뢰 관계를 GCP에 설정하는 방식으로, 키 파일 없이 동작한다.

```bash
# 로컬에서 실행 (VM에서 나온 뒤)

# GitHub Actions 전용 서비스 계정 만들기
# — GCP에서 이 계정에만 이미지 푸시 권한을 줄 것
gcloud iam service-accounts create kcpilot-github-actions \
  --display-name="KCpilot GitHub Actions"

export PROJECT_ID=$(gcloud config get-value project)
export SA_EMAIL="kcpilot-github-actions@${PROJECT_ID}.iam.gserviceaccount.com"

# 이 서비스 계정에 Artifact Registry 쓰기 권한만 부여
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/artifactregistry.writer"

# Workload Identity Pool 생성
# — "GitHub Actions에서 오는 토큰을 신뢰하는 그룹"
gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions Pool"

# Pool에 GitHub OIDC Provider 등록
# — GitHub이 발급한 토큰을 이 Pool이 검증할 수 있게 연결
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# "hamin-kang/kcpilot 저장소에서 온 요청"에게 서비스 계정 사용 허가
export POOL_ID=$(gcloud iam workload-identity-pools describe github-pool \
  --location=global --format="value(name)")

gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/hamin-kang/kcpilot"
```

---

## 6. GitHub Secrets 등록

**무엇**: GitHub Actions workflow가 참조하는 비밀값들을 GitHub에 저장한다.
GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret.

먼저 필요한 값들을 확인한다:

```bash
# GCP_WORKLOAD_IDENTITY_PROVIDER 값
gcloud iam workload-identity-pools providers describe github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --format="value(name)"
# 출력 예: projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider

# GCP_SERVICE_ACCOUNT 값
echo $SA_EMAIL

# VM 공인 IP
gcloud compute instances describe kcpilot-vm \
  --zone=asia-northeast3-a \
  --format="value(networkInterfaces[0].accessConfigs[0].natIP)"

# VM SSH 키 (gcloud ssh를 한 번 이상 했으면 자동 생성돼 있음)
cat ~/.ssh/google_compute_engine
```

등록할 Secrets:

| Secret 이름 | 설명 | 값 |
|---|---|---|
| `GCP_PROJECT_ID` | GCP 프로젝트 ID | `YOUR_PROJECT_ID` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Workload Identity Provider 리소스명 | 위 명령어 출력값 |
| `GCP_SERVICE_ACCOUNT` | GitHub Actions용 서비스 계정 이메일 | 위 명령어 출력값 |
| `VM_HOST` | VM 공인 IP | 위 명령어 출력값 |
| `VM_USER` | VM SSH 사용자명 | VM 안에서 `whoami` 결과 |
| `VM_SSH_KEY` | VM SSH 개인키 | `cat ~/.ssh/google_compute_engine` 출력 전체 |

---

## 7. 첫 배포 전: pgvector 데이터 적재

**무엇**: 법령·품목 임베딩 데이터는 Docker 이미지 안에 없다. PostgreSQL 볼륨에 저장되어야 한다.
GitHub Actions CD가 돌기 전에 한 번만 수동으로 파이프라인을 실행해서 데이터를 넣어야 한다.

로컬에서 SSH 터널로 VM의 PostgreSQL에 직접 붙어서 실행하는 게 가장 단순하다.

```bash
# 터미널 1: SSH 터널 열기 (VM 5432 → 로컬 5432로 포워딩)
gcloud compute ssh kcpilot-vm --zone=asia-northeast3-a -- -L 5432:localhost:5432

# 터미널 2: 로컬에서 파이프라인 실행 (터널이 열린 상태에서)
cd ai-service
DATABASE_URL=postgresql+psycopg://YOUR_DB_USER:YOUR_DB_PASSWORD@localhost:5432/kcpilot \
  uv run python pipeline/parse_laws.py
DATABASE_URL=postgresql+psycopg://YOUR_DB_USER:YOUR_DB_PASSWORD@localhost:5432/kcpilot \
  uv run python pipeline/parse_emc_pdf.py
DATABASE_URL=postgresql+psycopg://YOUR_DB_USER:YOUR_DB_PASSWORD@localhost:5432/kcpilot \
  uv run python pipeline/ingest.py
```

---

## 8. 배포 확인

모든 설정이 끝나면 `main` 브랜치에 push할 때마다 GitHub Actions CD가 자동으로 실행된다.

```bash
# VM에서 컨테이너 상태 확인
gcloud compute ssh kcpilot-vm --zone=asia-northeast3-a
docker compose -f ~/kcpilot/docker-compose.prod.yaml ps

# 서비스 접속 확인 (VM_IP는 실제 IP로 교체)
curl http://VM_IP:8000/ai/health   # ai-service
curl http://VM_IP:8080/actuator/health  # backend (actuator 설정 시)
# frontend: 브라우저에서 http://VM_IP:3000
```
