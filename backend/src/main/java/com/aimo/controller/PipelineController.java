package com.aimo.controller;

import com.aimo.entity.Pipeline;
import com.aimo.repository.IncidentRepository;
import com.aimo.repository.PipelineRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/pipelines")
public class PipelineController {

    private final PipelineRepository pipelineRepo;
    private final IncidentRepository incidentRepo;

    public PipelineController(PipelineRepository pipelineRepo, IncidentRepository incidentRepo) {
        this.pipelineRepo = pipelineRepo;
        this.incidentRepo = incidentRepo;
    }

    record CreateRequest(@NotBlank String name, String description) {}

    @GetMapping
    public ResponseEntity<?> list(@AuthenticationPrincipal String email) {
        return ResponseEntity.ok(pipelineRepo.findByOwnerEmail(email));
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
