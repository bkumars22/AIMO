package com.aimo.repository;

import com.aimo.entity.Incident;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

import java.util.List;
import java.util.UUID;

public interface IncidentRepository extends JpaRepository<Incident, UUID>, JpaSpecificationExecutor<Incident> {
    List<Incident> findByPipelineIdAndStatus(UUID pipelineId, Incident.IncidentStatus status);
    Page<Incident> findByPipelineId(UUID pipelineId, Pageable pageable);
}
