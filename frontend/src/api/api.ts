import axios, { type AxiosRequestConfig } from 'axios'
import { MOCK_PIPELINES, MOCK_INCIDENTS, MOCK_COST_TREND, MOCK_FAITHFULNESS_TREND } from './mockData'

// ── Env vars ──────────────────────────────────────────────────────────────────
// `||` (not `??`) on purpose — the GitHub Pages build passes these as empty
// strings, not unset, so a nullish check alone would never fall through.
export const AI_ENGINE = import.meta.env.VITE_AI_ENGINE_URL || 'http://localhost:8001'
export const BACKEND   = import.meta.env.VITE_API_BASE_URL  || 'http://localhost:8080'
export const WS_URL    = import.meta.env.VITE_WS_URL        || 'ws://localhost:8001/ws/dashboard'

// GitHub Pages is static-only — no live backend exists to call there. When
// VITE_DEMO_MODE=true (set by .github/workflows/pages.yml), every apiClient
// request is intercepted here and answered from mockData.ts instead of
// going over the network, so the public dashboard shows realistic-looking
// data instead of permanent zeros/connection errors.
export const IS_DEMO = import.meta.env.VITE_DEMO_MODE === 'true'

function mockOk(data: unknown, config: AxiosRequestConfig) {
  return Promise.resolve({ data, status: 200, statusText: 'OK', headers: {}, config })
}

const mockAdapter = (config: AxiosRequestConfig) => {
  const url    = (config.url ?? '').split('?')[0]
  const method = (config.method ?? 'get').toLowerCase()

  if (method === 'get' && url === '/api/pipelines') {
    return mockOk(MOCK_PIPELINES, config)
  }
  if (method === 'get' && url === '/api/pipelines/metrics') {
    return mockOk({ cost_trend: MOCK_COST_TREND, faithfulness_trend: MOCK_FAITHFULNESS_TREND }, config)
  }
  if (method === 'get' && url === '/api/incidents') {
    const status = (config.params as { status?: string } | undefined)?.status
    const items = status ? MOCK_INCIDENTS.filter((i) => i.status === status) : MOCK_INCIDENTS
    return mockOk({ items, total: items.length }, config)
  }
  const incidentGet = /^\/api\/incidents\/([^/]+)$/.exec(url)
  if (method === 'get' && incidentGet) {
    const inc = MOCK_INCIDENTS.find((i) => i.id === incidentGet[1])
    if (!inc) return Promise.reject({ response: { status: 404, data: { error: 'Not found' } } })
    return mockOk(inc, config)
  }
  const incidentResolve = /^\/api\/incidents\/([^/]+)\/resolve$/.exec(url)
  if (method === 'patch' && incidentResolve) {
    const inc = MOCK_INCIDENTS.find((i) => i.id === incidentResolve[1])
    if (inc) {
      inc.status = 'RESOLVED'
      const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data
      inc.resolution_notes = body?.resolution_notes
      inc.false_positive = !!body?.false_positive
    }
    return mockOk({}, config)
  }
  return mockOk({}, config)
}

// ── Axios client with auth header injection ───────────────────────────────────
export const apiClient = axios.create({
  baseURL: BACKEND,
  ...(IS_DEMO ? { adapter: mockAdapter as AxiosRequestConfig['adapter'] } : {}),
})

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
