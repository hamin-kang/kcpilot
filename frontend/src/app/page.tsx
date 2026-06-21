"use client";

import { useState, useEffect } from "react";
import type {
  AssessmentRequest,
  AssessmentResult,
  Certification,
} from "@/app/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";

const HAIRDRYER: AssessmentRequest = {
  product_name: "헤어드라이어",
  usage: "가정용",
  uses_electricity: true,
  for_children: false,
  specs: "220V 1200W",
};

const CONFIDENCE_STYLE: Record<string, string> = {
  HIGH: "bg-green-100 text-green-800 border-green-300",
  MEDIUM: "bg-amber-100 text-amber-800 border-amber-300",
  LOW: "bg-red-100 text-red-800 border-red-300",
};

export default function Home() {
  const [form, setForm] = useState<AssessmentRequest>(HAIRDRYER);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AssessmentResult | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/assessments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) {
        throw new Error(`서버 오류 (${res.status}): ${await res.text()}`);
      }
      setResult((await res.json()) as AssessmentResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6 sm:p-10">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">KCpilot — KC 인증 사전진단</h1>
        <p className="mt-1 text-sm text-gray-500">
          제품 정보를 입력하면 적용 인증·시험항목·리콜 사례를 진단합니다 (스파이크).
        </p>
      </header>

      <form onSubmit={submit} className="space-y-4 rounded-lg border p-5">
        <div>
          <label className="block text-sm font-medium">제품명</label>
          <input
            className="mt-1 w-full rounded border px-3 py-2"
            value={form.product_name}
            onChange={(e) => setForm({ ...form, product_name: e.target.value })}
            required
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium">용도</label>
            <input
              className="mt-1 w-full rounded border px-3 py-2"
              value={form.usage}
              onChange={(e) => setForm({ ...form, usage: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium">주요 사양</label>
            <input
              className="mt-1 w-full rounded border px-3 py-2"
              value={form.specs ?? ""}
              onChange={(e) => setForm({ ...form, specs: e.target.value })}
              placeholder="예: 220V 1200W"
            />
          </div>
        </div>
        <div className="flex gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.uses_electricity}
              onChange={(e) =>
                setForm({ ...form, uses_electricity: e.target.checked })
              }
            />
            전기 사용
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.for_children}
              onChange={(e) =>
                setForm({ ...form, for_children: e.target.checked })
              }
            />
            어린이 대상
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 rounded bg-black px-4 py-2 text-white disabled:opacity-60"
          >
            {loading && (
              <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
            )}
            {loading ? "진단 중…" : "진단하기"}
          </button>
          <button
            type="button"
            onClick={() => setForm(HAIRDRYER)}
            className="rounded border px-4 py-2 text-sm"
          >
            헤어드라이어 예시 채우기
          </button>
        </div>
      </form>

      {error && (
        <div className="mt-6 rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading && <LoadingView />}
      {result && <ResultView result={result} />}
    </main>
  );
}

const STEPS = [
  { label: "카테고리 분류", desc: "제품 유형 파악" },
  { label: "법령 검색 (RAG)", desc: "pgvector에서 관련 법령 검색" },
  { label: "인증 식별", desc: "시험항목·기관 도출" },
  { label: "리콜 사례 검색", desc: "유사 사고 이력 조회" },
  { label: "자기비판 검증", desc: "근거 충실성 재검토" },
];

function LoadingView() {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setActive((p) => Math.min(p + 1, STEPS.length - 1)), 6000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="mt-8 rounded-lg border p-6">
      <div className="mb-5 flex items-center gap-3">
        <svg className="h-5 w-5 animate-spin text-gray-500" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <span className="font-semibold">AI 진단 중 — LangGraph 워크플로우 실행</span>
      </div>
      <ol className="space-y-3">
        {STEPS.map((step, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold
              ${i < active ? "bg-green-500 text-white"
              : i === active ? "bg-black text-white"
              : "bg-gray-100 text-gray-400"}`}>
              {i < active ? "✓" : i + 1}
            </span>
            <div>
              <p className={`text-sm font-medium ${i <= active ? "text-gray-900" : "text-gray-400"}`}>
                {step.label}
              </p>
              <p className="text-xs text-gray-400">{step.desc}</p>
            </div>
            {i === active && (
              <span className="ml-auto text-xs text-gray-400 animate-pulse">처리 중…</span>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-5 text-xs text-gray-400">Gemini 호출 포함 — 완료까지 15~30초 소요됩니다</p>
    </div>
  );
}

function ResultView({ result }: { result: AssessmentResult }) {
  return (
    <section className="mt-8 space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">{result.product_name} 진단 결과</h2>
        <span className="text-xs text-gray-400">정보 기준일 {result.info_date}</span>
      </div>

      {result.needs_expert_review && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm font-medium text-red-700">
          ⚠ 전문가 상담 권장 — 동일 축에서 인증등급이 경합하거나 신뢰도가 낮은 인증이 있습니다. 최종 판단은 공식 기관에 확인하세요.
        </div>
      )}

      {result.categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {result.categories.map((c) => (
            <span key={c} className="rounded-full bg-gray-100 px-3 py-1 text-xs">
              {c}
            </span>
          ))}
        </div>
      )}

      {/* 적용 인증 */}
      <div className="space-y-3">
        <h3 className="font-semibold">적용 인증</h3>
        {result.certifications.length === 0 && (
          <p className="text-sm text-gray-500">식별된 인증이 없습니다.</p>
        )}
        {result.certifications.map((cert, i) => (
          <CertCard key={i} cert={cert} />
        ))}
      </div>

      {/* 시험 항목 */}
      {result.test_items.length > 0 && (
        <div>
          <h3 className="font-semibold">
            시험 항목 ({result.test_items.length}개)
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {result.test_items.map((t, i) => (
              <li key={i}>
                <span className="font-medium">{t.name}</span>
                {t.description ? ` — ${t.description}` : ""}
                {t.related_certification ? (
                  <span className="text-gray-400"> ({t.related_certification})</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 시험기관 추천 */}
      {result.recommended_labs.length > 0 && (
        <div>
          <h3 className="font-semibold">시험기관 추천</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {result.recommended_labs.map((l, i) => (
              <li key={i}>
                <span className="font-medium">{l.name}</span> — {l.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 리콜 사례 */}
      {result.recall_cases.length > 0 && (
        <div>
          <h3 className="font-semibold">유사 리콜 사례</h3>
          <div className="mt-2 space-y-2">
            {result.recall_cases.map((r, i) => (
              <div
                key={i}
                className="rounded border border-orange-200 bg-orange-50 p-3 text-sm"
              >
                <div className="font-medium">{r.title}</div>
                <div className="text-gray-600">{r.reason}</div>
                <div className="mt-1 text-xs text-gray-400">
                  {r.date} · {r.source}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 추론 로그 (F-06) */}
      {result.reasoning_log.length > 0 && (
        <details className="rounded border p-3 text-sm">
          <summary className="cursor-pointer font-semibold">
            단계별 추론 로그 보기
          </summary>
          <ol className="mt-2 space-y-2">
            {result.reasoning_log.map((s, i) => (
              <li key={i}>
                <span className="font-medium">{s.step}</span>: {s.detail}
              </li>
            ))}
          </ol>
        </details>
      )}

      <p className="border-t pt-4 text-xs text-gray-400">{result.disclaimer}</p>
    </section>
  );
}

function CertCard({ cert }: { cert: Certification }) {
  const badge =
    CONFIDENCE_STYLE[cert.confidence] ?? "bg-gray-100 text-gray-700 border-gray-300";
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <div className="font-medium">
          <span className="rounded bg-gray-800 px-2 py-0.5 text-xs text-white">
            {cert.axis}
          </span>{" "}
          {cert.type}
          {cert.category ? (
            <span className="ml-2 text-xs text-gray-400">{cert.category}</span>
          ) : null}
        </div>
        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${badge}`}>
          {cert.confidence}
        </span>
      </div>
      <p className="mt-2 text-sm text-gray-700">{cert.reason}</p>
      {cert.citations.length > 0 && (
        <div className="mt-3 space-y-1">
          {cert.citations.map((c, i) => (
            <div key={i} className="rounded bg-gray-50 p-2 text-xs">
              <span className="font-medium">근거: {c.law} {c.article}</span>
              <p className="mt-0.5 text-gray-500">{c.snippet}</p>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 text-[10px] text-gray-300">
        rag {cert.rag_score} · llm {cert.llm_score} · score {cert.confidence_score}
      </div>
    </div>
  );
}
