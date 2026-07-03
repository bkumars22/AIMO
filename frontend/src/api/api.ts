import axios from 'axios'

// ── Env vars ──────────────────────────────────────────────────────────────────
export const AI_ENGINE = import.meta.env.VITE_AI_ENGINE_URL ?? 'http://localhost:8001'
export const BACKEND   = import.meta.env.VITE_API_BASE_URL  ?? 'http://localhost:8080'
export const WS_URL    = import.meta.env.VITE_WS_URL        ?? 'ws://localhost:8001/ws/dashboard'

// ── Axios client with auth header injection ───────────────────────────────────
export const apiClient = axios.create({ baseURL: BACKEND })

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('aimo_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Types ─────────────────────────────────────────────────────────────────────

export type IncidentType =
  | 'HALLUCINATION'
  | 'COST_SPIKE'
  | 'COMPLIANCE_DRIFT'
  | 'LATENCY_DEGRADATION'
  | 'PROMPT_INJECTION'
  | 'QUALITY_DEGRADATION'
  | 'ANOMALY'

export type Severity       = 'P0' | 'P1' | 'P2' | 'P3'
export type IncidentStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'

export interface Incident {
  id:             string
  pipeline_id:    string
  pipeline_name?: string
  run_id?:        string
  incident_type:  IncidentType
  severity:       Severity
  status:         IncidentStatus
  title:          string
  root_cause?:    string
  suggested_fix?: string
  evidence?:      Record<string, unknown>
  resolution_notes?: string
  false_positive?:   boolean
  created_at?:    string
  updated_at?:    string
  resolved_at?:   string
}

export interface Pipeline {
  id:           string
  name:         string
  description?: string
  health_score: number
  owner_email?: string
  created_at?:  string
}

// ── API helpers ───────────────────────────────────────────────────────────────

export async function getIncidents(params?: {
  pipeline_id?: string
  type?: IncidentType
  severity?: Severity
  status?: IncidentStatus
  page?: number
  limit?: number
}): Promise<{ items: Incident[]; total: number }> {
  const r = await apiClient.get('/api/incidents', { params })
  return r.data
}

export async function getIncident(id: string): Promise<Incident> {
  const r = await apiClient.get(`/api/incidents/${id}`)
  return r.data
}

export async function getPipelines(): Promise<Pipeline[]> {
  const r = await apiClient.get('/api/pipelines')
  return r.data
}

export async function resolveIncident(id: string, notes: string, falsePositive = false): Promise<void> {
  await apiClient.patch(`/api/incidents/${id}/resolve`, {
    resolution_notes: notes,
    false_positive: falsePositive,
  })
}
