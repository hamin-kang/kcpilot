"""KC 인증 사전진단 LangGraph 워크플로우.

흐름 (requirements.md F-03):
  classify  → 카테고리 분류 + 검색 질의 생성
  retrieve  → pgvector 법령 검색 (진짜 RAG)
  diagnose  → 검색된 법령에만 근거해 인증/시험항목/기관 식별
  recall    → 리콜 사례 벡터 검색
  critique  → 자기비판으로 인증별 llm_score 산출

신뢰도(Phase 1): 코사인 유사도(rag_score)는 "관련 법령을 찾았나"의 검색 게이트로만
쓰고, 근거 충실성 판단(llm_score = critique 노드)이 신뢰도를 결정한다 → HIGH/MEDIUM/LOW.
두 값은 척도가 달라(코사인≈0.6~0.8 압축 vs LLM 판단) MIN/평균이 부적절하다.
반환은 schemas.AssessmentResult.
"""
from __future__ import annotations

from datetime import date
from typing import TypedDict

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

import settings
from llm import cosine_distance_to_similarity, get_chat, get_vector_store
from schemas import (
    AssessmentRequest,
    AssessmentResult,
    Certification,
    Citation,
    LabRecommendation,
    RecallCase,
    ReasoningStep,
    TestItem,
)


# ---------- LangGraph 상태 ----------
class AssessmentState(TypedDict, total=False):
    request: dict              # AssessmentRequest.model_dump()
    categories: list[str]
    search_query: str
    law_hits: list[dict]       # {ref, law, article, axis, category, text, similarity}
    cert_drafts: list[dict]
    test_items: list[dict]
    labs: list[dict]
    recall_cases: list[dict]
    critiques: list[dict]      # {type, llm_score, note}
    reasoning_log: list[dict]


# ---------- 노드별 LLM 출력 스키마 ----------
class ClassifyOut(BaseModel):
    categories: list[str] = Field(description="전기용품/생활용품/어린이제품 중 해당하는 것")
    search_query: str = Field(description="관련 법령을 찾기 위한 핵심 키워드 검색 질의")
    reasoning: str = Field(description="분류 근거 한두 문장")


class CertDraft(BaseModel):
    axis: str = Field(description="안전 또는 전자파")
    type: str = Field(description="안전인증/안전확인/공급자적합성확인/적합인증/적합등록/자기적합확인 등")
    category: str | None = Field(default=None, description="전기용품/생활용품/어린이제품")
    reason: str = Field(description="이 인증이 필요한 이유")
    cited_refs: list[int] = Field(default_factory=list, description="근거가 된 [근거N]의 번호 목록")


class TestItemDraft(BaseModel):
    name: str
    description: str | None = None
    related_certification: str | None = None


class LabDraft(BaseModel):
    name: str = Field(description="KTL/KTR/KTC 등")
    reason: str


class DiagnoseOut(BaseModel):
    certifications: list[CertDraft]
    test_items: list[TestItemDraft]
    recommended_labs: list[LabDraft]
    reasoning: str


class CertCritique(BaseModel):
    index: int = Field(description="평가 대상 인증의 번호 (목록에 제시된 번호 그대로)")
    llm_score: float = Field(description="0.0~1.0, 법령 근거가 이 결론을 뒷받침하는 정도")
    note: str = Field(description="의심되는 점이나 모호함")


class CritiqueOut(BaseModel):
    critiques: list[CertCritique]
    overall_note: str


# ---------- 유틸 ----------
def _product_brief(req: dict) -> str:
    parts = [f"제품명: {req['product_name']}", f"용도: {req['usage']}"]
    parts.append("전기 사용: 예" if req.get("uses_electricity") else "전기 사용: 아니오")
    parts.append("어린이 대상: 예" if req.get("for_children") else "어린이 대상: 아니오")
    if req.get("specs"):
        parts.append(f"주요 사양: {req['specs']}")
    return "\n".join(parts)


def _log(state: AssessmentState, step: str, detail: str) -> list[dict]:
    log = list(state.get("reasoning_log", []))
    log.append({"step": step, "detail": detail})
    return log


# ---------- 노드 ----------
def classify_node(state: AssessmentState) -> dict:
    req = state["request"]
    llm = get_chat().with_structured_output(ClassifyOut)
    prompt = (
        "너는 KC 인증 사전진단 보조원이다. 아래 제품을 보고 "
        "전기용품/생활용품/어린이제품 중 해당하는 카테고리를 모두 고르고, "
        "관련 법령을 검색하기 위한 핵심 키워드 검색 질의를 만들어라.\n\n"
        f"{_product_brief(req)}"
    )
    out: ClassifyOut = llm.invoke(prompt)
    return {
        "categories": out.categories,
        "search_query": out.search_query,
        "reasoning_log": _log(
            state, "① 카테고리 분류",
            f"카테고리: {', '.join(out.categories) or '미정'} · {out.reasoning}",
        ),
    }


def retrieve_node(state: AssessmentState) -> dict:
    req = state["request"]
    query = state.get("search_query") or _product_brief(req)
    store = get_vector_store(settings.LAW_COLLECTION)
    pairs = store.similarity_search_with_score(query, k=settings.TOP_K_LAW)

    hits: list[dict] = []
    for i, (doc, distance) in enumerate(pairs, start=1):
        m = doc.metadata or {}
        hits.append({
            "ref": i,
            "law": m.get("law", "(미상)"),
            "article": m.get("article", ""),
            "axis": m.get("axis"),
            "category": m.get("category"),
            "text": doc.page_content,
            "similarity": round(cosine_distance_to_similarity(distance), 3),
        })

    summary = "; ".join(f"[근거{h['ref']}] {h['law']} {h['article']}(유사도 {h['similarity']})" for h in hits) or "검색 결과 없음"
    return {
        "law_hits": hits,
        "reasoning_log": _log(state, "② 법령 검색(RAG)", f"질의='{query}' → {summary}"),
    }


def _format_law_context(hits: list[dict]) -> str:
    if not hits:
        return "(검색된 법령 없음)"
    blocks = []
    for h in hits:
        blocks.append(
            f"[근거{h['ref']}] ({h['axis']}축 / {h['category']}) "
            f"{h['law']} {h['article']}\n{h['text']}"
        )
    return "\n\n".join(blocks)


def diagnose_node(state: AssessmentState) -> dict:
    req = state["request"]
    hits = state.get("law_hits", [])
    llm = get_chat().with_structured_output(DiagnoseOut)
    prompt = (
        "너는 KC 인증 사전진단 전문가다. 아래 [근거]로 제공된 법령 텍스트에만 근거하여 "
        "제품에 적용되는 인증을 빠짐없이 식별하라.\n"
        "중요 규칙:\n"
        "- 한 제품이 안전 축과 전자파 축에 동시에 걸릴 수 있다. 둘 다 해당하면 둘 다 식별하라.\n"
        "- 제공된 근거에 없는 내용은 절대 지어내지 마라. 근거가 부족하면 그 인증은 빼거나 reason에 한계를 명시하라.\n"
        "- 각 인증의 cited_refs에는 근거가 된 [근거N]의 번호를 넣어라.\n"
        "- 시험 항목과 추천 시험기관(KTL/KTR/KTC)도 근거 범위에서 제시하라.\n\n"
        f"=== 제품 ===\n{_product_brief(req)}\n\n"
        f"=== 근거 법령 ===\n{_format_law_context(hits)}"
    )
    out: DiagnoseOut = llm.invoke(prompt)
    cert_summary = "; ".join(f"{c.axis}-{c.type}" for c in out.certifications) or "식별된 인증 없음"
    return {
        "cert_drafts": [c.model_dump() for c in out.certifications],
        "test_items": [t.model_dump() for t in out.test_items],
        "labs": [l.model_dump() for l in out.recommended_labs],
        "reasoning_log": _log(state, "③ 인증·시험항목·기관 식별", f"{cert_summary} · {out.reasoning}"),
    }


def recall_node(state: AssessmentState) -> dict:
    req = state["request"]
    query = state.get("search_query") or req["product_name"]
    store = get_vector_store(settings.RECALL_COLLECTION)
    try:
        pairs = store.similarity_search_with_score(query, k=settings.TOP_K_RECALL)
    except Exception:
        pairs = []
    cases = []
    for doc, _ in pairs:
        m = doc.metadata or {}
        cases.append({
            "title": m.get("title", ""),
            "product": m.get("product", ""),
            "reason": m.get("reason", ""),
            "date": m.get("date"),
            "source": m.get("source"),
        })
    return {
        "recall_cases": cases,
        "reasoning_log": _log(state, "④ 유사 리콜 검색", f"{len(cases)}건 검색"),
    }


def critique_node(state: AssessmentState) -> dict:
    drafts = state.get("cert_drafts", [])
    hits = {h["ref"]: h for h in state.get("law_hits", [])}
    if not drafts:
        return {
            "critiques": [],
            "reasoning_log": _log(state, "⑤ 자기비판", "식별된 인증이 없어 평가 생략"),
        }

    # 각 인증과 그 근거 텍스트를 번호와 함께 비판 대상으로 제시
    lines = []
    for i, d in enumerate(drafts):
        cited = " / ".join(
            f"{hits[r]['law']} {hits[r]['article']}: {hits[r]['text'][:120]}"
            for r in d.get("cited_refs", []) if r in hits
        ) or "(인용 근거 없음)"
        lines.append(f"{i}. [{d['axis']}-{d['type']}] 근거: {cited}")

    llm = get_chat().with_structured_output(CritiqueOut)
    prompt = (
        "아래는 1차 진단 결과다. 각 인증에 대해 '인용된 법령 근거가 실제로 그 결론을 "
        "뒷받침하는가'를 비판적으로 평가하라. 근거가 명확하면 높게(0.85+), "
        "근거가 빈약하거나 해석이 모호하면 낮게(0.65 미만) 점수를 매겨라. "
        "거짓 자신감을 경계하라. 각 평가에는 위 목록의 번호(index)를 그대로 넣어라.\n\n"
        + "\n".join(lines)
    )
    out: CritiqueOut = llm.invoke(prompt)
    note = "; ".join(f"#{c.index}={c.llm_score}" for c in out.critiques)
    return {
        "critiques": [c.model_dump() for c in out.critiques],
        "reasoning_log": _log(state, "⑤ 자기비판", f"{note} · {out.overall_note}"),
    }


# ---------- 그래프 ----------
def _build_graph():
    g = StateGraph(AssessmentState)
    g.add_node("classify", classify_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("diagnose", diagnose_node)
    g.add_node("recall", recall_node)
    g.add_node("critique", critique_node)
    g.add_edge(START, "classify")
    g.add_edge("classify", "retrieve")
    g.add_edge("retrieve", "diagnose")
    g.add_edge("diagnose", "recall")
    g.add_edge("recall", "critique")
    g.add_edge("critique", END)
    return g.compile()


_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ---------- 최종 조립 ----------
def _assemble(state: AssessmentState) -> AssessmentResult:
    hits = {h["ref"]: h for h in state.get("law_hits", [])}
    critique_map = {c["index"]: c for c in state.get("critiques", [])}

    certifications: list[Certification] = []
    for i, d in enumerate(state.get("cert_drafts", [])):
        refs = [r for r in d.get("cited_refs", []) if r in hits]
        sims = [hits[r]["similarity"] for r in refs]
        rag_score = round(sum(sims) / len(sims), 3) if sims else 0.0

        crit = critique_map.get(i, {})
        llm_score = round(float(crit.get("llm_score", 0.0)), 3)

        # --- 신뢰도 산출 (Phase 1) ---
        # rag_score(코사인)는 검색 관련성 게이트로만, 신뢰도 자체는 충실성(llm_score)이 결정.
        if not refs:
            # 인용 근거가 전혀 없음 → 결론을 뒷받침할 법령이 없음
            confidence_score = 0.0
        elif rag_score < settings.RETRIEVAL_FLOOR:
            # 검색이 빈약 → 충실성이 높아도 MEDIUM 밑으로 강등(최대 LOW)
            confidence_score = round(min(llm_score, settings.MEDIUM_THRESHOLD - 0.01), 3)
        else:
            # 관련 법령을 찾음 → 충실성 판단이 신뢰도를 결정
            confidence_score = llm_score
        citations = [
            Citation(
                law=hits[r]["law"],
                article=hits[r]["article"],
                snippet=hits[r]["text"][:200],
            )
            for r in refs
        ]
        certifications.append(Certification(
            axis=d["axis"],
            type=d["type"],
            category=d.get("category"),
            reason=d["reason"],
            confidence=settings.confidence_label(confidence_score),
            rag_score=rag_score,
            llm_score=llm_score,
            confidence_score=confidence_score,
            citations=citations,
        ))

    needs_expert = any(c.confidence == "LOW" for c in certifications) or not certifications

    return AssessmentResult(
        product_name=state["request"]["product_name"],
        categories=state.get("categories", []),
        certifications=certifications,
        test_items=[TestItem(**t) for t in state.get("test_items", [])],
        recommended_labs=[LabRecommendation(**l) for l in state.get("labs", [])],
        recall_cases=[RecallCase(**r) for r in state.get("recall_cases", [])],
        reasoning_log=[ReasoningStep(**s) for s in state.get("reasoning_log", [])],
        needs_expert_review=needs_expert,
        disclaimer=settings.DISCLAIMER,
        info_date=date.today().isoformat(),
    )


def run_assessment(request: AssessmentRequest) -> AssessmentResult:
    final_state = _graph().invoke({"request": request.model_dump(), "reasoning_log": []})
    return _assemble(final_state)
