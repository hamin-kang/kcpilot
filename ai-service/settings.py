"""환경설정 한 곳 모음. main.py가 load_dotenv()를 호출하므로 여기서도 보장한다."""
import os

from dotenv import load_dotenv

load_dotenv()

# --- 외부 연결 ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://hamin:1234@localhost:5432/kcpilot",
)
# 국가법령정보 OPEN API 기관코드(OC) — 로그인 이메일의 @ 앞부분. pipeline/fetch_laws.py가 사용.
LAW_API_OC = os.getenv("LAW_API_OC", "")
# 제품안전정보센터(safetykorea) Open API 키 — pipeline/fetch_recalls.py가 사용. 이메일 신청 후 발급.
SAFETYKOREA_API_KEY = os.getenv("SAFETYKOREA_API_KEY", "")

# --- 모델 ---
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/gemini-embedding-001")
# gemini-embedding-001은 MRL로 출력 차원 조정 가능(기본 3072). 768로 고정해
# pgvector 컬럼 차원과 일치시킨다. 코사인 거리는 크기 불변이라 정규화 걱정 없음.
EMBEDDING_DIM = 768

# --- pgvector 컬렉션 이름 ---
LAW_COLLECTION = "kc_legal"       # 법령 조항 임베딩
RECALL_COLLECTION = "kc_recalls"  # 리콜 사례 임베딩 (샘플)

# --- 검색 ---
TOP_K_LAW = 6      # 법령 검색 시 끌어올 청크 수
TOP_K_RECALL = 3   # 리콜 사례 검색 시 끌어올 건수

# --- 신뢰도 임계값 (requirements.md 4.2.1) ---
# 주의: 이 임계값은 아직 정답셋으로 보정되지 않은 상속값이다(Phase 3에서 측정 필요).
HIGH_THRESHOLD = 0.85    # >= 0.85 → HIGH
MEDIUM_THRESHOLD = 0.65  # >= 0.65 → MEDIUM, 그 미만 → LOW

# --- 검색 관련성 바닥 (Phase 1) ---
# 코사인 유사도(rag_score)는 "관련 법령을 찾았나"의 검색 신호지 신뢰도가 아니다.
# 인용 근거의 평균 유사도가 이 값 미만이면 "관련 법령을 사실상 못 찾은 것"으로 보고
# 신뢰도를 LOW로 강등한다(게이트). 이 값도 정답셋으로 보정 대상 — Phase 3.
RETRIEVAL_FLOOR = 0.45

# --- 고정 표시 문구 ---
DISCLAIMER = "본 서비스는 사전 참고용이며 법적 효력이 없습니다. 최종 판단은 한국제품안전관리원·시험기관 등 공식 기관에 확인하십시오."


def confidence_label(score: float) -> str:
    """confidenceScore(0~1)를 HIGH/MEDIUM/LOW 라벨로 변환."""
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"
