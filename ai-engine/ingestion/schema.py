"""
Pydantic schemas for AIMO ingestion API.
These are the API contract — finalized before feature code.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SpanPayload(BaseModel):
    """
    Posted by @aimo_trace after each LangGraph node completes.
    One span = one node execution within a pipeline run.
    """
    pipeline_id:        str   = Field(..., description="'ARIA' | 'SCIP' | 'QAIP' | 'ZENTRAVIX'")
    pipeline_name:      str
    run_id:             str   = Field(..., description="Unique ID for the full pipeline execution")
    span_id:            Optional[str] = None
    node_name:          str   = Field(..., description="LangGraph node name, e.g. 'teach_socratically'")
    model_id:           Optional[str] = Field(None, description="LLM model ID; null for non-LLM nodes")
    input_text:         str   = Field(..., max_length=10_000)
    output_text:        str   = Field(..., max_length=10_000)
    context:            Optional[str] = Field(None, max_length=20_000,
                                              description="RAG chunks injected into prompt; null if no RAG")
    prompt_tokens:      int   = Field(0, ge=0)
    completion_tokens:  int   = Field(0, ge=0)
    cost_usd:           float = Field(0.0, ge=0.0)
    latency_ms:         int   = Field(0, ge=0)
    timestamp:          datetime = Field(default_factory=datetime.utcnow)
    user_id:            Optional[str] = Field(None, description="student_id for ARIA; null for other pipelines")
    langsmith_run_id:   Optional[str] = None


class RunPayload(BaseModel):
    """Posted at the end of a complete pipeline execution."""
    pipeline_id:        str
    run_id:             str
    status:             str   = Field(..., pattern="^(completed|failed|timeout)$")
    total_cost_usd:     float = Field(0.0, ge=0.0)
    total_tokens:       int   = Field(0, ge=0)
    latency_ms:         int   = Field(0, ge=0)
    node_count:         int   = Field(0, ge=0)
    model_ids:          list[str] = Field(default_factory=list)
    error:              Optional[str] = None
    started_at:         datetime
    completed_at:       datetime


class PipelineRegisterPayload(BaseModel):
    """Register a pipeline so AIMO can monitor it."""
    name:               str   = Field(..., min_length=1, max_length=100)
    description:        Optional[str] = None
    node_count:         int   = Field(..., ge=1)
    environment:        str   = Field("production", pattern="^(production|staging|dev)$")


class EvalResultPayload(BaseModel):
    """Posted after a compliance eval run (from run_eval.py or scheduler)."""
    pipeline_id:        str
    dataset_version:    str
    total_cases:        int
    auto_scored:        int
    passed:             int
    failed:             int
    compliance_pct:     float = Field(..., ge=0.0, le=100.0)
    trigger:            str   = Field(..., pattern="^(scheduled|manual|incident_triggered|sampling)$")
    case_results:       list[dict] = Field(default_factory=list)


class IncidentAcknowledgePayload(BaseModel):
    acknowledged_by:    str   = Field(..., min_length=1)
    note:               Optional[str] = None


class IncidentResolvePayload(BaseModel):
    resolved_by:        str   = Field(..., min_length=1)
    root_cause:         Optional[str] = None
