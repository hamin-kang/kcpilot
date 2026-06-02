package com.kcpilot.assessment;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

public interface AssessmentRepository extends JpaRepository<Assessment, Long> {

    /** 최신순 이력 조회 (F-08). */
    List<Assessment> findAllByOrderByCreatedAtDesc();
}
