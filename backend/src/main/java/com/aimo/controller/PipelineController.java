package com.aimo.controller;

import com.aimo.entity.Pipeline;
import com.aimo.entity.PipelineRun;
import com.aimo.repository.IncidentRepository;
import com.aimo.repository.PipelineRepository;
import com.aimo.repository.PipelineRunRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/pipelines")
public class PipelineController {

    private final PipelineRepository pipelineRepo;
    private final IncidentRepository incidentRepo;
    private final PipelineRunRepository pipelineRunRepo;

    public PipelineController(PipelineRepository pipelineRepo, IncidentRepository incidentRepo,
                               PipelineRunRepository pipelineRunRepo) {
        this.pipelineRepo = pipelineRepo;
        this.incidentRepo = incidentRepo;
        this.pipelineRunRepo = pipelineRunRepo;
    }

    record CreateRequest(@NotBlank String name, String description) {}

    @GetMapping
    public ResponseEntity<?> list(@AuthenticationPrincipal String email) {
        return ResponseEntity.ok(pipelineRepo.findByOwnerEmail(email));
    }

    // Fleet-wide cost + faithfulness trend across all of the current user's
    // pipelines, for the dashboard's "Cost Trend (7d)" / "Faithfulness Trend
    // (7d)" charts. pipeline_runs rows come from the ai-engine's monitoring
    // pipeline (storage/repositories.py save_run — see monitoring_agent.py's
    // store_and_update node).
    @GetMapping("/metrics")
    public ResponseEntity<?> fleetMetrics(
            @AuthenticationPrincipal String email,
            @RequestParam(defaultValue = "7") int days) {

        List<UUID> pipelineIds = pipelineRepo.findByOwnerEmail(email).stream()
                .map(Pipeline::getId)
                .collect(Collectors.toList());

        if (pipelineIds.isEmpty()) {
            return ResponseEntity.ok(Map.of("cost_trend", List.of(), "faithfulness_trend", List.of()));
        }

        Instant since = Instant.now().minusSeconds((long) days * 24 * 3600);
        List<PipelineRun> runs = pipelineRunRepo
                .findByPipelineIdInAndStartedAtAfterOrderByStartedAtAsc(pipelineIds, since);

        DateTimeFormatter dayFmt = DateTimeFormatter.ISO_LOCAL_DATE;
        Map<String, List<BigDecimal>> costByDay = new LinkedHashMap<>();
        Map<String, List<BigDecimal>> faithByDay = new LinkedHashMap<>();

        for (PipelineRun run : runs) {
            String day = LocalDate.ofInstant(run.getStartedAt(), ZoneOffset.UTC).format(dayFmt);
            if (run.getCostUsd() != null) {
                costByDay.computeIfAbsent(day, d -> new ArrayList<>()).add(run.getCostUsd());
            }
            if (run.getFaithfulnessScore() != null) {
                faithByDay.computeIfAbsent(day, d -> new ArrayList<>()).add(run.getFaithfulnessScore());
            }
        }

        List<Map<String, Object>> costTrend = costByDay.entrySet().stream()
                .map(e -> Map.<String, Object>of("date", e.getKey(), "cost", average(e.getValue())))
                .collect(Collectors.toList());
        List<Map<String, Object>> faithTrend = faithByDay.entrySet().stream()
                .map(e -> Map.<String, Object>of("date", e.getKey(), "faithfulness", average(e.getValue())))
                .collect(Collectors.toList());

        return ResponseEntity.ok(Map.of("cost_trend", costTrend, "faithfulness_trend", faithTrend));
    }

    private static BigDecimal average(List<BigDecimal> values) {
        BigDecimal sum = values.stream().reduce(BigDecimal.ZERO, BigDecimal::add);
        return sum.divide(BigDecimal.valueOf(values.size()), 6, RoundingMode.HALF_UP);
    }

    @PostMapping
    public ResponseEntity<?> create(
            @Valid @RequestBody CreateRequest req,
            @AuthenticationPrincipal String email) {
        var pipeline = new Pipeline();
        pipeline.setName(req.name());
        pipeline.setDescription(req.description());
        pipeline.setOwnerEmail(email);
        pipelineRepo.save(pipeline);
        return ResponseEntity.status(HttpStatus.CREATED).body(pipeline);
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> get(@PathVariable UUID id) {
        return pipelineRepo.findById(id)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PutMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN') or @pipelineOwnerCheck.check(#id, authentication)")
    public ResponseEntity<?> update(@PathVariable UUID id, @RequestBody Map<String, String> body) {
        var pipeline = pipelineRepo.findById(id).orElse(null);
        if (pipeline == null) return ResponseEntity.notFound().build();
        if (body.containsKey("name"))        pipeline.setName(body.get("name"));
        if (body.containsKey("description")) pipeline.setDescription(body.get("description"));
        pipelineRepo.save(pipeline);
        return ResponseEntity.ok(pipeline);
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> delete(@PathVariable UUID id) {
        if (!pipelineRepo.existsById(id)) return ResponseEntity.notFound().build();
        pipelineRepo.deleteById(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{id}/incidents")
    public ResponseEntity<?> incidents(
            @PathVariable UUID id,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        var result = incidentRepo.findByPipelineId(id, PageRequest.of(page, size));
        return ResponseEntity.ok(Map.of(
                "items", result.getContent(),
                "total", result.getTotalElements(),
                "page", page
        ));
    }

    @GetMapping("/{id}/metrics/summary")
    public ResponseEntity<?> metricsSummary(@PathVariable UUID id) {
        var pipeline = pipelineRepo.findById(id).orElse(null);
        if (pipeline == null) return ResponseEntity.notFound().build();
        // Phase 1: aggregate from run_metrics table
        return ResponseEntity.ok(Map.of(
                "pipeline_id",  id,
                "health_score", pipeline.getHealthScore(),
                "message",      "Full metrics aggregation — Phase 1"
        ));
    }
}
