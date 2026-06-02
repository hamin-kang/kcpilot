package com.kcpilot.assessment;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * 진단 이력 엔티티(F-08의 씨앗).
 *
 * <p>스파이크 단계라 요청/결과 JSON을 통째로 text 컬럼에 보관한다. 정규화는
 * 핵심 기능이 검증된 뒤로 미룬다. {@code ddl-auto: update}로 테이블이 자동 생성된다.
 */
@Entity
@Table(name = "assessment")
@Getter
@Setter
@NoArgsConstructor
public class Assessment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String productName;

    @Column(columnDefinition = "text")
    private String requestJson;

    @Column(columnDefinition = "text")
    private String resultJson;

    private Instant createdAt;
}
