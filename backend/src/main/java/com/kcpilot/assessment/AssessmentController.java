package com.kcpilot.assessment;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.fasterxml.jackson.databind.JsonNode;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;

@RestController
@RequestMapping("/api/assessments")
@RequiredArgsConstructor
public class AssessmentController {

    private final AssessmentService service;

    /** 제품 정보를 받아 진단을 실행하고 결과 JSON을 반환한다. */
    @PostMapping
    public JsonNode create(@Valid @RequestBody AssessmentRequest request) {
        return service.diagnose(request);
    }

    /** 진단 이력(최신순) 조회. */
    @GetMapping
    public List<AssessmentSummary> history() {
        return service.history();
    }
}
