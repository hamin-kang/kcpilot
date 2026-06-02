package com.kcpilot.assessment;

import com.fasterxml.jackson.annotation.JsonProperty;

import jakarta.validation.constraints.NotBlank;

/**
 * 진단 요청 DTO.
 *
 * <p>JSON 키는 ai-service(FastAPI)의 snake_case 스키마와 동일하게 맞춘다. 그래야
 * 프론트→백엔드→ai-service 전 구간에서 같은 JSON 모양을 그대로 흘려보낼 수 있다.
 */
public record AssessmentRequest(
        @JsonProperty("product_name") @NotBlank String productName,
        @JsonProperty("usage") @NotBlank String usage,
        @JsonProperty("uses_electricity") boolean usesElectricity,
        @JsonProperty("for_children") boolean forChildren,
        @JsonProperty("specs") String specs) {
}
