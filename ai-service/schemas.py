"""ai-service 입출력 Pydantic 스키마.

F-02(입력) / F-04(결과 표시) / F-06(추론 로그) / 4.2.1(신뢰도) 요구사항에 맞춘다.
API 응답에는 라벨만 노출하는 게 정책이지만(4.2.1), 스파이크 단계에서는
디버깅 편의를 위해 점수(rag/llm/confidence)도 함께 내려보낸다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------- 입력 (F-02) ----------
class AssessmentRequest(BaseModel):
    product_name: str = Field(..., description="제품명", examples=["헤어드라이어"])
    usage: str = Field(..., description="제품 용도", examples=["가정용"])
    uses_electricity: bool = Field(True, description="전기 사용 여부")
    for_children: bool = Field(False, description="어린이 대상 여부")
    specs: str | None = Field(
        None, description="주요 사양 자유 텍스트", examples=["220V 1200W"]
    )


# ---------- 출력 구성 요소 (F-04) ----------
class Citation(BaseModel):
    law: str = Field(..., description="법령명")
    article: str = Field(..., description="조항/별표 위치")
    snippet: str = Field(..., description="근거가 된 법령 텍스트 발췌")


class Certification(BaseModel):
    axis: str = Field(..., description="인증 축: 안전 | 전자파")
    type: str = Field(..., description="안전인증/안전확인/공급자적합성확인/적합인증/적합등록/자기적합확인 등")
    category: str | None = Field(None, description="전기용품/생활용품/어린이제품")
    reason: str = Field(..., description="해당 인증이 필요하다고 판단한 근거 설명")
    confidence: str = Field(..., description="HIGH | MEDIUM | LOW")
    rag_score: float = Field(..., description="RAG 유사도 점수 (0~1, 디버깅용)")
    llm_score: float = Field(..., description="LLM 자기비판 점수 (0~1, 디버깅용)")
    confidence_score: float = Field(..., description="MIN(rag, llm), 디버깅용")
    citations: list[Citation] = Field(default_factory=list)


class TestItem(BaseModel):
    name: str = Field(..., description="시험 항목명")
    description: str | None = Field(None, description="설명")
    related_certification: str | None = Field(None, description="관련 인증 type")


class LabRecommendation(BaseModel):
    name: str = Field(..., description="시험기관: KTL/KTR/KTC 등")
    reason: str = Field(..., description="추천 이유")


class RecallCase(BaseModel):
    title: str
    product: str
    reason: str
    date: str | None = None
    source: str | None = None


class ReasoningStep(BaseModel):
    """F-06 단계별 추론 로그."""
    step: str = Field(..., description="단계 이름")
    detail: str = Field(..., description="해당 단계에서 일어난 일")


# ---------- 최종 결과 (F-04) ----------
class AssessmentResult(BaseModel):
    product_name: str
    categories: list[str] = Field(default_factory=list, description="적용 카테고리(전기/생활/어린이)")
    certifications: list[Certification] = Field(default_factory=list)
    test_items: list[TestItem] = Field(default_factory=list)
    recommended_labs: list[LabRecommendation] = Field(default_factory=list)
    recall_cases: list[RecallCase] = Field(default_factory=list)
    reasoning_log: list[ReasoningStep] = Field(default_factory=list)
    needs_expert_review: bool = Field(
        False, description="LOW 인증이 1개라도 있으면 true (전문가 상담 권장 배지)"
    )
    disclaimer: str = ""
    info_date: str = Field(..., description="정보 기준일 (YYYY-MM-DD)")
