package com.kcpilot.assessment;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * ai-service(FastAPI)의 /ai/run-assessment 를 호출하는 클라이언트.
 *
 * <p>진단 결과 JSON은 중첩 구조라 Java DTO로 다시 모델링하지 않고 {@link JsonNode}로
 * 그대로 받아 패스스루한다(스키마 중복·드리프트 방지). 백엔드는 중개 + 저장만 담당.
 */
@Component
public class AiServiceClient {

    private final String baseUrl;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    public AiServiceClient(@Value("${ai-service.base-url:http://localhost:8000}") String baseUrl, ObjectMapper objectMapper) {
        this.baseUrl = baseUrl;
        this.objectMapper = objectMapper;

        // LangGraph 워크플로우가 Gemini 호출을 여러 번 하므로 넉넉하게 120초 설정
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout((int) Duration.ofSeconds(5).toMillis());
        factory.setReadTimeout((int) Duration.ofSeconds(120).toMillis());
        this.restTemplate = new RestTemplate(factory);
    }

    public JsonNode runAssessment(AssessmentRequest request) {
        ObjectNode payload = objectMapper.createObjectNode()
                .put("product_name", request.productName())
                .put("usage", request.usage())
                .put("uses_electricity", request.usesElectricity())
                .put("for_children", request.forChildren())
                .put("specs", request.specs());

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        return restTemplate.postForObject(
                baseUrl + "/ai/run-assessment",
                new HttpEntity<>(payload, headers),
                JsonNode.class);
    }
}
