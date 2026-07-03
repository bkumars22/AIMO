package com.aimo.repository;

import com.aimo.entity.Pipeline;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface PipelineRepository extends JpaRepository<Pipeline, UUID> {
    List<Pipeline> findByOwnerEmail(String ownerEmail);
}
