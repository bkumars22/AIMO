// Static stand-in data for the GitHub Pages demo (bkumars22.github.io/AIMO).
// GitHub Pages only serves static files — there's no live Postgres/Redis/
// Spring Boot/FastAPI behind it, so this axios adapter (wired up in api.ts,
// gated by VITE_DEMO_MODE) intercepts every apiClient call and returns
// canned-but-realistic data instead of a network request. Same pattern as
// SCIP's build/mock-api.js.

import type { Incident, Pipeline } from './api'

const DAY_MS = 24 * 60 * 60 * 1000
const isoDaysAgo = (n: number) => new Date(Date.now() - n * DAY_MS).toISOString()

export const MOCK_PIPELINES: Pipeline[] = [
  { id: 'pl-qaip', name: 'QAIP Monitor', description: 'QA test-pipeline cost + faithfulness', health_score: 91, created_at: isoDaysAgo(42) },
  { id: 'pl-scip', name: 'SCIP Monitor', description: 'Supply-chain supplier-risk LLM calls', health_score: 74, created_at: isoDaysAgo(38) },
  { id: 'pl-aria', name: 'ARIA Monitor', description: 'AI tutor compliance + injection defense', health_score: 88, created_at: isoDaysAgo(51) },
]

export const MOCK_INCIDENTS: Incident[] = [
  {
    id: 'inc-1', pipeline_id: 'pl-aria', pipeline_name: 'ARIA Monitor', run_id: 'run-8841',
    incident_type: 'PROMPT_INJECTION', severity: 'P0', status: 'OPEN',
    title: 'Jailbreak attempt detected on ARIA tutor',
    root_cause: 'Student submitted a DAN-mode prompt attempting to bypass content filters.',
    suggested_fix: 'Pattern already blocked the response; no action needed beyond monitoring for repeat attempts.',
    created_at: isoDaysAgo(0.2),
  },
  {
    id: 'inc-2', pipeline_id: 'pl-scip', pipeline_name: 'SCIP Monitor', run_id: 'run-8790',
    incident_type: 'HALLUCINATION', severity: 'P1', status: 'OPEN',
    title: 'Low faithfulness score on supplier risk explanation',
    root_cause: 'Faithfulness 0.34 — model referenced a compliance clause not present in retrieved context.',
    suggested_fix: 'Expand retrieval context window for supplier-risk explanation node.',
    created_at: isoDaysAgo(0.6),
  },
  {
    id: 'inc-3', pipeline_id: 'pl-scip', pipeline_name: 'SCIP Monitor', run_id: 'run-8712',
    incident_type: 'COST_SPIKE', severity: 'P2', status: 'OPEN',
    title: 'Cost 4.1x baseline on SCIP supplier-risk node',
    root_cause: 'Large CSV import triggered extra chunking + re-embedding calls.',
    created_at: isoDaysAgo(1.1),
  },
  {
    id: 'inc-4', pipeline_id: 'pl-qaip', pipeline_name: 'QAIP Monitor', run_id: 'run-8650',
    incident_type: 'COMPLIANCE_DRIFT', severity: 'P1', status: 'RESOLVED',
    title: 'Compliance rate declining on QAIP pipeline',
    root_cause: 'Faithfulness scores trended down for 3 consecutive days.',
    resolution_notes: 'Root prompt reverted after AIPQ flagged a recent edit as the cause.',
    created_at: isoDaysAgo(3), resolved_at: isoDaysAgo(2),
  },
  {
    id: 'inc-5', pipeline_id: 'pl-aria', pipeline_name: 'ARIA Monitor', run_id: 'run-8511',
    incident_type: 'LATENCY_DEGRADATION', severity: 'P2', status: 'RESOLVED',
    title: 'Latency 3.2x baseline on ARIA generate node',
    root_cause: 'Groq rate limit triggered retry with exponential backoff.',
    resolution_notes: 'Added a second model fallback; latency back to baseline.',
    created_at: isoDaysAgo(4), resolved_at: isoDaysAgo(4),
  },
]

const round = (n: number, dp = 4) => Number(n.toFixed(dp))

export const MOCK_COST_TREND = Array.from({ length: 7 }, (_, i) => ({
  date: isoDaysAgo(6 - i).slice(0, 10),
  cost: round(0.006 + Math.sin(i / 2) * 0.0015 + (i === 5 ? 0.012 : 0)),
}))

export const MOCK_FAITHFULNESS_TREND = Array.from({ length: 7 }, (_, i) => ({
  date: isoDaysAgo(6 - i).slice(0, 10),
  faithfulness: round(0.9 - (i === 3 ? 0.4 : 0) + Math.sin(i) * 0.03, 3),
}))
