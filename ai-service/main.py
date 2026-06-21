from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from schemas import AssessmentRequest, AssessmentResult
from workflow import run_assessment

load_dotenv()

app = FastAPI(
    title="KCpilot AI Service",
    version="0.1.0",
    description="KC 인증 사전진단 AI 서비스",
)


@app.get("/ai/health")
async def health_check():
    return {"status": "ok", "service": "ai-service"}


@app.post("/ai/run-assessment", response_model=AssessmentResult)
async def run_assessment_endpoint(request: AssessmentRequest) -> AssessmentResult:
    """제품 정보를 받아 LangGraph 진단 워크플로우를 실행한다.

    흐름: 카테고리 분류 → 법령 RAG 검색 → 인증·시험항목·기관 식별
          → 리콜 검색 → 자기비판 → 인증별 신뢰도 라벨.
    """
    try:
        return run_assessment(request)
    except Exception as exc:  # noqa: BLE001 - 스파이크: 원인 그대로 노출
        raise HTTPException(status_code=500, detail=f"진단 실패: {exc}") from exc
