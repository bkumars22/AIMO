package com.aimo.controller;

import com.aimo.entity.Incident;
import com.aimo.repository.IncidentRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/incidents")
public class IncidentController {

    private final IncidentRepository incidentRepo;

    public IncidentController(IncidentRepository incidentRepo) {
        this.incidentRepo = incidentRepo;
    }

    record ResolveRequest(@NotBlank String resolutionNotes, boolean falsePositive) {}
    record CommentRequest(@NotBlank String body) {}

    @GetMapping
    public ResponseEntity<?> list(
            @RequestParam(required = false) String pipelineId,
            @RequestParam(required = false) String severity,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String type,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int limit) {

        Specification<Incident> spec = Specification.where(null);
        if (pipelineId != null) {
            UUID pid = UUID.fromString(pipelineId);
            spec = spec.and((root, q, cb) -> cb.equal(root.get("pipelineId"), pid));
        }
        if (severity != null) {
            spec = spec.and((root, q, cb) -> cb.equal(root.get("severity"), Incident.Severity.valueOf(severity)));
        }
        if (status != null) {
            spec = spec.and((root, q, cb) -> cb.equal(root.get("status"), Incident.IncidentStatus.valueOf(status)));
        }
        if (type != null) {
            spec = spec.and((root, q, cb) -> cb.equal(root.get("incidentType"), type));
        }

        var result = incidentRepo.findAll(spec, PageRequest.of(page, limit));
        return ResponseEntity.ok(Map.of(
                "items", result.getContent(),
                "total", result.getTotalElements(),
                "page",  page,
                "limit", limit
        ));
    }

    @GetMapping("/{id}")
    public ResponseEntity<?> get(@PathVariable UUID id) {
        return incidentRepo.findById(id)
                .<ResponseEntity<?>>map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PatchMapping("/{id}")
    public ResponseEntity<?> patch(@PathVariable UUID id, @RequestBody Map<String, Object> updates) {
        var incident = incidentRepo.findById(id).orElse(null);
        if (incident == null) return ResponseEntity.notFound().build();
        if (updates.containsKey("status")) {
            incident.setStatus(Incident.IncidentStatus.valueOf((String) updates.get("status")));
        }
        incidentRepo.save(incident);
        return ResponseEntity.ok(incident);
    }

    @PostMapping("/{id}/comments")
    public ResponseEntity<?> addComment(@PathVariable UUID id, @Valid @RequestBody CommentRequest req) {
        // Phase 1: persist to incident_comments table
        return ResponseEntity.ok(Map.of(
                "incident_id", id,
                "body",        req.body(),
                "message",     "Comment storage — Phase 1"
        ));
    }

    @GetMapping("/{id}/timeline")
    public ResponseEntity<?> timeline(@PathVariable UUID id) {
        var incident = incidentRepo.findById(id).orElse(null);
        if (incident == null) return ResponseEntity.notFound().build();
        // Phase 1: query audit_log table for this incident
        return ResponseEntity.ok(Map.of(
                "incident_id", id,
                "events",      java.util.List.of(
                        Map.of("event", "DETECTED", "timestamp", incident.getCreatedAt()),
                        Map.of("event", "STATUS", "status", incident.getStatus(), "timestamp", incident.getUpdatedAt())
                )
        ));
    }
}
