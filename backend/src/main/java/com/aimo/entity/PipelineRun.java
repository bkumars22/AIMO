package com.aimo.entity;

import jakarta.persistence.*;
import lombok.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

/**
 * Maps only the columns the /api/pipelines/metrics trend endpoint needs.
 * The full pipeline_runs table (V1 + V7) has more columns than this —
 * intentionally partial mapping to keep Hibernate's ddl-auto=validate
 * check narrow and avoid the kind of entity/schema drift that broke
 * the Incident entity (see V8__incident_api_fields.sql).
 */
@Entity
@Table(name = "pipeline_runs")
@Getter @Setter @NoArgsConstructor
public class PipelineRun {

    @Id
    private UUID id;

    @Column(name = "pipeline_id", nullable = false)
    private UUID pipelineId;

    @Column(name = "cost_usd")
    private BigDecimal costUsd;

    @Column(name = "faithfulness_score")
    private BigDecimal faithfulnessScore;

    @Column(name = "started_at", nullable = false)
    private Instant startedAt;
}
