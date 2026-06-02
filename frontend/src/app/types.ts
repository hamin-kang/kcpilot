// ai-service AssessmentResult 와 동일한 snake_case 스키마.
// 백엔드는 ai-service 응답을 그대로 패스스루하므로 키가 snake_case다.

export interface Citation {
  law: string;
  article: string;
  snippet: string;
}

export interface Certification {
  axis: string;
  type: string;
  category: string | null;
  reason: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  rag_score: number;
  llm_score: number;
  confidence_score: number;
  citations: Citation[];
}

export interface TestItem {
  name: string;
  description: string | null;
  related_certification: string | null;
}

export interface LabRecommendation {
  name: string;
  reason: string;
}

export interface RecallCase {
  title: string;
  product: string;
  reason: string;
  date: string | null;
  source: string | null;
}

export interface ReasoningStep {
  step: string;
  detail: string;
}

export interface AssessmentResult {
  product_name: string;
  categories: string[];
  certifications: Certification[];
  test_items: TestItem[];
  recommended_labs: LabRecommendation[];
  recall_cases: RecallCase[];
  reasoning_log: ReasoningStep[];
  needs_expert_review: boolean;
  disclaimer: string;
  info_date: string;
}

export interface AssessmentRequest {
  product_name: string;
  usage: string;
  uses_electricity: boolean;
  for_children: boolean;
  specs: string | null;
}
