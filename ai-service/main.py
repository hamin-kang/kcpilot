from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="KCpilot AI Service",
    version="0.1.0",
    description="KC 인증 사전진단 AI 서비스"
)

@app.get("/ai/health")
async def health_check():
    return {"status": "ok", "service": "ai-service"}

@app.post("/ai/run-assessment")
async def run_assessment(request: dict):
    # TODO: LangGraph 워크플로우 연결
    return {"status": "not_implemented"}
