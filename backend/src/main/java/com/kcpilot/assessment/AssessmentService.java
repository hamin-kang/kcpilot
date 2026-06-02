package com.kcpilot.assessment;

import java.time.Instant;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import lombok.RequiredArgsConstructor;

@Service
@RequiredArgsConstructor
public class AssessmentService {

    private static final Logger log = LoggerFactory.getLogger(AssessmentService.class);

    private final AiServiceClient aiServiceClient;
    private final AssessmentRepository repository;
    private final ObjectMapper objectMapper;

    /** ai-service 진단 실행 후 이력 저장. 저장 실패가 응답을 막지 않도록 예외를 삼킨다. */
    public JsonNode diagnose(AssessmentRequest request) {
        JsonNode result = aiServiceClient.runAssessment(request);
        save(request, result);
        return result;
    }

    private void save(AssessmentRequest request, JsonNode result) {
        try {
            Assessment entity = new Assessment();
            entity.setProductName(request.productName());
            entity.setRequestJson(objectMapper.writeValueAsString(request));
            entity.setResultJson(result.toString());
            entity.setCreatedAt(Instant.now());
            repository.save(entity);
        } catch (Exception e) {
            log.warn("진단 이력 저장 실패 (응답에는 영향 없음): {}", e.getMessage());
        }
    }

    public List<AssessmentSummary> history() {
        return repository.findAllByOrderByCreatedAtDesc().stream()
                .map(a -> new AssessmentSummary(a.getId(), a.getProductName(), a.getCreatedAt()))
                .toList();
    }
}
