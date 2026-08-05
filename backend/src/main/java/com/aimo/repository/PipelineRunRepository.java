package com.aimo.repository;

import com.aimo.entity.PipelineRun;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public interface PipelineRunRepository extends JpaRepository<PipelineRun, UUID> {
    List<PipelineRun> findByPipelineIdInAndStartedAtAfterOrderByStartedAtAsc(
            List<UUID> pipelineIds, Instant since);
}
