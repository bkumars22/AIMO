package com.aimo.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/alerts")
public class AlertController {

    @GetMapping("/settings")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> getSettings() {
        // Phase 1: load from alert_rules table (seeded via V4__alerting.sql)
        return ResponseEntity.ok(Map.of(
                "slack_webhook_configured", false,
                "email_configured",         false,
                "message", "Alert settings — Phase 1"
        ));
    }

    @PutMapping("/settings")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> updateSettings(@RequestBody Map<String, Object> settings) {
        // Phase 1: persist to alert_config table
        return ResponseEntity.ok(Map.of("updated", true, "settings", settings));
    }

    @PostMapping("/test")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> testAlert(@RequestBody Map<String, String> body) {
        String channel = body.getOrDefault("channel", "slack");
        // Phase 1: call AlertDispatcherService
        return ResponseEntity.ok(Map.of(
                "sent", false,
                "channel", channel,
                "message", "Test alert dispatch — Phase 1"
        ));
    }
}
