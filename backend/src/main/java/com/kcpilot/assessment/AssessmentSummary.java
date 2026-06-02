package com.kcpilot.assessment;

import java.time.Instant;

/** 이력 목록용 요약 DTO (결과 JSON 전체는 제외). */
public record AssessmentSummary(Long id, String productName, Instant createdAt) {
}
