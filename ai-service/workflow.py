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
    item_hits: list[dict]      # {item_name, cert_level, axis, category, law, article, similarity}
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


def _product_query(req: dict) -> str:
    """품목 분류표 매칭용 질의. 법령 검색 질의와 달리 '제품 정체성'에 집중한다
    (예: '헤어드라이어 가정용 220V'). 법령 키워드가 섞이면 엉뚱한 품목이 잡힌다.
    """
    parts = [req["product_name"], req.get("usage") or ""]
    if req.get("specs"):
        parts.append(req["specs"])
    return " ".join(p for p in parts if p).strip()


def _strong_items(state: AssessmentState) -> list[dict]:
    """신뢰 바닥을 넘긴 품목 매칭만(권위 있는 인증등급 출처)."""
    return [
        h for h in state.get("item_hits", [])
        if h["similarity"] >= settings.ITEM_MATCH_FLOOR
    ]


def _best_item_for_draft(draft: dict, strong_items: list[dict]) -> dict | None:
    """이 인증(축+등급)을 뒷받침하는 품목 매칭 중 최고 유사도 1건."""
    return max(
        (h for h in strong_items
         if h["axis"] == draft.get("axis") and h["cert_level"] == draft.get("type")),
        key=lambda h: h["similarity"], default=None,
    )


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


# 안전 법령 조문은 전기용품·생활용품을 함께 다뤄 category가 이 결합값으로 묶여 저장된다.
_COMBINED_SAFETY_CATEGORY = "전기용품,생활용품"


def _build_law_filter(state: AssessmentState) -> dict | None:
    """classify가 결정한 카테고리로 검색 범위를 좁히는 필터를 만든다.

    축(안전/전자파)이 아니라 category로 거른다 — 축으로 거르면 '안전+전자파 동시
    인증'을 한 번에 식별하지 못해 핵심 기능이 깨진다. 전기용품/생활용품 질의는
    안전 조문의 결합 카테고리("전기용품,생활용품")도 함께 매칭되도록 확장한다.
    """
    cats = state.get("categories") or []
    if not cats:
        return None
    vals = set(cats)
    if {"전기용품", "생활용품"} & vals:
        vals.add(_COMBINED_SAFETY_CATEGORY)
    return {"category": {"$in": sorted(vals)}}


def retrieve_node(state: AssessmentState) -> dict:
    req = state["request"]
    query = state.get("search_query") or _product_brief(req)
    store = get_vector_store(settings.LAW_COLLECTION)

    law_filter = _build_law_filter(state)
    pairs = store.similarity_search_with_score(query, k=settings.TOP_K_LAW, filter=law_filter)
    # 폴백: 필터가 너무 좁아 0건이면 필터를 풀고 재검색
    if not pairs and law_filter is not None:
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


def match_items_node(state: AssessmentState) -> dict:
    """별표 품목(kc_items)에서 제품을 매칭해 cert_level의 권위 있는 출처를 얻는다.

    법령 조문 검색(retrieve_node)과 분리한 이유: 품목은 "이 제품이 무슨 인증등급인가"를
    품목명 매칭으로 정밀하게 찾고, cert_level은 본문 추론이 아니라 metadata에서 그대로
    꺼낸다. 이러면 LLM이 긴 본문에서 등급을 잘못 읽는 오류가 구조적으로 사라진다.
    """
    req = state["request"]
    query = _product_query(req)
    store = get_vector_store(settings.ITEM_COLLECTION)

    item_filter = _build_law_filter(state)
    pairs = store.similarity_search_with_score(query, k=settings.TOP_K_ITEM, filter=item_filter)
    if not pairs and item_filter is not None:  # 필터가 너무 좁아 0건이면 풀고 재검색
        pairs = store.similarity_search_with_score(query, k=settings.TOP_K_ITEM)

    hits: list[dict] = []
    for doc, distance in pairs:
        m = doc.metadata or {}
        hits.append({
            "item_name": m.get("item_name") or doc.page_content,
            "cert_level": m.get("cert_level"),
            "axis": m.get("axis"),
            "category": m.get("category"),
            "law": m.get("law", "(미상)"),
            "article": m.get("article", ""),
            "similarity": round(cosine_distance_to_similarity(distance), 3),
        })

    strong = [h for h in hits if h["similarity"] >= settings.ITEM_MATCH_FLOOR]
    summary = "; ".join(
        f"{h['item_name']}({h['axis']}/{h['cert_level']}, 유사도 {h['similarity']})" for h in strong
    ) or "신뢰할 만한 품목 매칭 없음"
    return {
        "item_hits": hits,
        "reasoning_log": _log(state, "③ 품목 분류표 매칭", summary),
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


def _format_item_context(item_hits: list[dict]) -> str:
    """신뢰 바닥을 넘긴 품목 매칭만 권위 있는 인증등급 출처로 제시한다."""
    strong = [h for h in item_hits if h["similarity"] >= settings.ITEM_MATCH_FLOOR]
    if not strong:
        return "(신뢰할 만한 품목 매칭 없음 — 아래 법령 본문으로만 판단하라)"
    return "\n".join(
        f"- {h['item_name']} → {h['axis']}축 / {h['cert_level']} / {h['category']} "
        f"[{h['law']} {h['article']}] (매칭도 {h['similarity']})"
        for h in strong
    )


def diagnose_node(state: AssessmentState) -> dict:
    req = state["request"]
    hits = state.get("law_hits", [])
    item_hits = state.get("item_hits", [])
    llm = get_chat().with_structured_output(DiagnoseOut)
    prompt = (
        "너는 KC 인증 사전진단 전문가다. 제품에 적용되는 인증을 빠짐없이 식별하라.\n"
        "두 종류의 자료가 주어진다:\n"
        "1) [품목 분류표 매칭] — 공식 별표에서 제품명으로 찾은 결과. cert_level의 권위 있는 출처다.\n"
        "2) [근거 법령] — 인증의 이유·절차·시험항목을 설명하는 조문.\n\n"
        "중요 규칙:\n"
        "- 품목 분류표 매칭에 나온 인증은 반드시 포함하고, type(인증등급)은 거기 적힌 값을 그대로 써라. "
        "법령 본문을 보고 인증등급을 새로 추론하지 마라.\n"
        "- 한 제품이 안전 축과 전자파 축에 동시에 걸릴 수 있다. 둘 다 매칭되면 둘 다 식별하라.\n"
        "- 분류표 매칭이 없는 인증을 본문 근거로 추가할 수는 있으나, 그때는 reason에 "
        "'분류표 미확인'이라고 한계를 명시하라.\n"
        "- 각 인증의 cited_refs에는 근거가 된 [근거N]의 번호를 넣어라.\n"
        "- 시험 항목과 추천 시험기관(KTL/KTR/KTC)도 근거 범위에서 제시하라.\n\n"
        f"=== 제품 ===\n{_product_brief(req)}\n\n"
        f"=== 품목 분류표 매칭 ===\n{_format_item_context(item_hits)}\n\n"
        f"=== 근거 법령 ===\n{_format_law_context(hits)}"
    )
    out: DiagnoseOut = llm.invoke(prompt)
    cert_summary = "; ".join(f"{c.axis}-{c.type}" for c in out.certifications) or "식별된 인증 없음"
    return {
        "cert_drafts": [c.model_dump() for c in out.certifications],
        "test_items": [t.model_dump() for t in out.test_items],
        "labs": [l.model_dump() for l in out.recommended_labs],
        "reasoning_log": _log(state, "④ 인증·시험항목·기관 식별", f"{cert_summary} · {out.reasoning}"),
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
        "reasoning_log": _log(state, "⑤ 유사 리콜 검색", f"{len(cases)}건 검색"),
    }


def critique_node(state: AssessmentState) -> dict:
    drafts = state.get("cert_drafts", [])
    hits = {h["ref"]: h for h in state.get("law_hits", [])}
    strong_items = _strong_items(state)
    if not drafts:
        return {
            "critiques": [],
            "reasoning_log": _log(state, "⑥ 자기비판", "식별된 인증이 없어 평가 생략"),
        }

    # 각 인증을 번호와 함께 제시한다. 두 종류의 뒷받침을 구분해서 보여준다:
    # (1) 분류표 매칭(인증등급의 공식 출처) (2) 인용 법령(이유·절차 근거)
    lines = []
    for i, d in enumerate(drafts):
        cited = " / ".join(
            f"{hits[r]['law']} {hits[r]['article']}: {hits[r]['text'][:120]}"
            for r in d.get("cited_refs", []) if r in hits
        ) or "(인용 근거 없음)"
        item = _best_item_for_draft(d, strong_items)
        table = (
            f"공식 분류표 등재 — {item['item_name']} ({item['law']} {item['article']}, 매칭도 {item['similarity']})"
            if item else "분류표 미확인"
        )
        lines.append(f"{i}. [{d['axis']}-{d['type']}] 분류표: {table} | 법령근거: {cited}")

    llm = get_chat().with_structured_output(CritiqueOut)
    prompt = (
        "아래는 1차 진단 결과다. 각 인증이 타당한지 비판적으로 평가하라(0.0~1.0).\n"
        "평가 기준:\n"
        "- 인증등급의 권위 있는 출처는 '공식 분류표 등재'다. 분류표에 등재된 인증은 "
        "법령 인용이 없더라도 그 사실만으로 낮게 매기지 마라(분류표가 곧 근거다). "
        "이 경우 0.85+를 기본으로 하되, 제품과 매칭된 품목이 어긋나 보이면 낮춰라.\n"
        "- '분류표 미확인'인 인증은 법령 인용이 결론을 뒷받침하는지로 평가하라. "
        "근거가 명확하면 높게(0.85+), 빈약하거나 모호하면 낮게(0.65 미만).\n"
        "- 거짓 자신감을 경계하라. 각 평가에는 위 목록의 번호(index)를 그대로 넣어라.\n\n"
        + "\n".join(lines)
    )
    out: CritiqueOut = llm.invoke(prompt)
    note = "; ".join(f"#{c.index}={c.llm_score}" for c in out.critiques)
    return {
        "critiques": [c.model_dump() for c in out.critiques],
        "reasoning_log": _log(state, "⑥ 자기비판", f"{note} · {out.overall_note}"),
    }


# ---------- 그래프 ----------
def _build_graph():
    g = StateGraph(AssessmentState)
    g.add_node("classify", classify_node)
    g.add_node("retrieve", retrieve_node)
    g.add_node("match_items", match_items_node)
    g.add_node("diagnose", diagnose_node)
    g.add_node("recall", recall_node)
    g.add_node("critique", critique_node)
    g.add_edge(START, "classify")
    g.add_edge("classify", "retrieve")
    g.add_edge("retrieve", "match_items")
    g.add_edge("match_items", "diagnose")
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
def _is_item_ambiguous(strong_items: list[dict]) -> bool:
    """같은 축에서 1순위와 인증등급이 다른 품목이 매칭 마진 이내로 붙어 있는가.

    그렇다면 어느 등급인지 분류표만으로는 결정할 수 없는 모호한 상황이다.
    """
    by_axis: dict[str, list[dict]] = {}
    for h in strong_items:
        by_axis.setdefault(h["axis"], []).append(h)
    for cands in by_axis.values():
        cands.sort(key=lambda h: h["similarity"], reverse=True)
        top = cands[0]
        for other in cands[1:]:
            if other["cert_level"] != top["cert_level"] and (
                top["similarity"] - other["similarity"] <= settings.ITEM_AMBIGUITY_MARGIN
            ):
                return True
    return False


def _assemble(state: AssessmentState) -> AssessmentResult:
    hits = {h["ref"]: h for h in state.get("law_hits", [])}
    strong_items = _strong_items(state)
    critique_map = {c["index"]: c for c in state.get("critiques", [])}

    certifications: list[Certification] = []
    for i, d in enumerate(state.get("cert_drafts", [])):
        refs = [r for r in d.get("cited_refs", []) if r in hits]
        sims = [hits[r]["similarity"] for r in refs]
        rag_score = round(sum(sims) / len(sims), 3) if sims else 0.0

        crit = critique_map.get(i, {})
        llm_score = round(float(crit.get("llm_score", 0.0)), 3)

        # 품목 분류표 앵커: cert_level의 권위 있는 출처(본문 추론이 아니라).
        item = _best_item_for_draft(d, strong_items)
        item_score = item["similarity"] if item else 0.0
        matched_item = item["item_name"] if item else None

        # --- 신뢰도 산출 (Phase 1 + 품목 앵커링) ---
        if item:
            # 공식 분류표에 등재된 인증 → 등급 자체는 권위 있게 확정됨. 최소 MEDIUM을
            # 보장하고, 그 위로는 충실성(llm_score)이 끌어올린다. 등급 모호성은 별도
            # needs_expert 플래그가 처리한다.
            confidence_score = round(max(llm_score, settings.MEDIUM_THRESHOLD), 3)
        elif not refs:
            # 분류표 매칭도 인용 근거도 없음 → 뒷받침 전무
            confidence_score = 0.0
        elif rag_score < settings.RETRIEVAL_FLOOR:
            # 검색이 빈약 → 충실성이 높아도 MEDIUM 밑으로 강등
            confidence_score = round(min(llm_score, settings.MEDIUM_THRESHOLD - 0.01), 3)
        else:
            # 본문 근거만 있고 분류표 미확인 → 등급 오판 위험, HIGH로 올리지 않음
            confidence_score = round(min(llm_score, settings.HIGH_THRESHOLD - 0.01), 3)
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
            matched_item=matched_item,
            rag_score=rag_score,
            item_score=item_score,
            llm_score=llm_score,
            confidence_score=confidence_score,
            citations=citations,
        ))

    # 같은 (축, 인증등급)이 여러 품목에서 중복 도출될 수 있다(예: 적합등록 품목 2개)
    # → 신뢰도가 가장 높은 1건만 남긴다.
    deduped: dict[tuple, Certification] = {}
    for c in certifications:
        key = (c.axis, c.type)
        if key not in deduped or c.confidence_score > deduped[key].confidence_score:
            deduped[key] = c
    certifications = list(deduped.values())

    needs_expert = (
        _is_item_ambiguous(strong_items)
        or any(c.confidence == "LOW" for c in certifications)
        or not certifications
    )

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
