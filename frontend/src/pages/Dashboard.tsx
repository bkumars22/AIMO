import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useWebSocket } from '../hooks/useWebSocket'
import { useIncidents } from '../hooks/useIncidents'
import { apiClient } from '../api/api'
import type { Incident } from '../api/api'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Pipeline {
  id: string
  name: string
  health_score: number
  active_incidents: { P0: number; P1: number; P2: number; P3: number }
}

interface CostPoint { date: string; cost: number }

// ── Severity badge ────────────────────────────────────────────────────────────

const SEV_STYLES: Record<string, string> = {
  P0: 'bg-red-900/60 text-red-400 border border-red-700',
  P1: 'bg-orange-900/60 text-orange-400 border border-orange-700',
  P2: 'bg-yellow-900/60 text-yellow-400 border border-yellow-700',
  P3: 'bg-gray-800 text-gray-400 border border-gray-700',
}

const SEV_DOT: Record<string, string> = {
  P0: 'bg-red-500', P1: 'bg-orange-500', P2: 'bg-yellow-500', P3: 'bg-gray-500',
}

const HEALTH_COLOR = (score: number) =>
  score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : '#ef4444'

// ── KPI Header ────────────────────────────────────────────────────────────────

function KpiBar({ incidents }: { incidents: Incident[] }) {
  const counts = { HALLUCINATION: 0, COST_SPIKE: 0, COMPLIANCE_DRIFT: 0, LATENCY_DEGRADATION: 0, PROMPT_INJECTION: 0 }
  for (const inc of incidents) {
    const t = inc.incident_type as keyof typeof counts
    if (t in counts) counts[t]++
  }
  const types = [
    { label: 'Hallucination', key: 'HALLUCINATION', icon: '🧠' },
    { label: 'Cost Spike',    key: 'COST_SPIKE',    icon: '💰' },
    { label: 'Compliance',    key: 'COMPLIANCE_DRIFT', icon: '📋' },
    { label: 'Latency',       key: 'LATENCY_DEGRADATION', icon: '⏱' },
    { label: 'Injection',     key: 'PROMPT_INJECTION', icon: '🛡' },
  ] as const

  return (
    <div className="grid grid-cols-5 gap-3 mb-6">
      {types.map(({ label, key, icon }) => (
        <div key={key} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <p className="text-xs text-gray-500 font-medium">{icon} {label}</p>
          <p className="text-2xl font-bold text-gray-100 mt-1">{counts[key]}</p>
          <p className="text-xs text-gray-600 mt-1">open incidents</p>
        </div>
      ))}
    </div>
  )
}

// ── Pipeline health grid ──────────────────────────────────────────────────────

function PipelineGrid({ pipelines }: { pipelines: Pipeline[] }) {
  if (!pipelines.length) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center text-gray-600 text-sm mb-6">
        No pipelines registered yet — POST to /pipelines/register to add one.
      </div>
    )
  }
  return (
    <div className="grid grid-cols-3 gap-3 mb-6">
      {pipelines.map((p) => {
        const color = HEALTH_COLOR(p.health_score)
        const openP0P1 = (p.active_incidents.P0 || 0) + (p.active_incidents.P1 || 0)
        return (
          <Link key={p.id} to={`/pipelines/${p.id}`}
            className="bg-gray-900 border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition-colors">
            <p className="text-xs text-gray-500 font-mono truncate mb-2">{p.name}</p>
            <p className="text-3xl font-bold" style={{ color }}>{p.health_score}</p>
            <p className="text-xs mt-1" style={{ color }}>health score</p>
            {openP0P1 > 0 && (
              <p className="text-xs text-red-400 mt-2">{openP0P1} critical open</p>
            )}
          </Link>
        )
      })}
    </div>
  )
}

// ── Live incident feed ────────────────────────────────────────────────────────

function IncidentFeedPanel({ incidents, connected }: { incidents: Incident[]; connected: boolean }) {
  const recent = [...incidents].slice(0, 20)
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-200">Live Incident Feed</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full font-mono ${connected ? 'bg-green-900 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
          {connected ? '● live' : '○ connecting…'}
        </span>
      </div>
      {recent.length === 0 ? (
        <p className="text-xs text-gray-600 py-6 text-center">No open incidents — your pipelines are healthy</p>
      ) : (
        <div className="space-y-2">
          {recent.map((inc) => (
            <Link key={inc.id} to={`/incidents/${inc.id}`}
              className="flex items-start gap-3 p-2 rounded hover:bg-gray-800 transition-colors">
              <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${SEV_DOT[inc.severity] || 'bg-gray-500'}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${SEV_STYLES[inc.severity] || ''}`}>
                    {inc.severity}
                  </span>
                  <span className="text-xs text-gray-500">{inc.incident_type}</span>
                </div>
                <p className="text-xs text-gray-300 mt-0.5 truncate">{inc.title}</p>
              </div>
              <p className="text-xs text-gray-600 flex-shrink-0">{inc.pipeline_name || '—'}</p>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Cost trend chart ──────────────────────────────────────────────────────────

function CostChart({ data }: { data: CostPoint[] }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-6">
      <h2 className="text-sm font-semibold text-gray-200 mb-4">Cost Trend (7d)</h2>
      {data.length === 0 ? (
        <div className="flex items-center justify-center h-36 text-gray-600 text-xs">No cost data yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={144}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v) => `$${v.toFixed(2)}`} />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #1f2937', fontSize: 12 }}
              formatter={(v: number) => [`$${v.toFixed(4)}`, 'cost']}
            />
            <Area type="monotone" dataKey="cost" stroke="#6366f1" fill="url(#costGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Faithfulness trend ────────────────────────────────────────────────────────

function FaithfulnessChart({ data }: { data: Array<{ date: string; faithfulness: number }> }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-6">
      <h2 className="text-sm font-semibold text-gray-200 mb-4">Faithfulness Trend (7d)</h2>
      {data.length === 0 ? (
        <div className="flex items-center justify-center h-36 text-gray-600 text-xs">No eval data yet</div>
      ) : (
        <ResponsiveContainer width="100%" height={144}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="faithGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #1f2937', fontSize: 12 }}
              formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, 'faithfulness']}
            />
            <Area type="monotone" dataKey="faithfulness" stroke="#22c55e" fill="url(#faithGrad)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Dashboard page ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { incidents: wsIncidents, connected } = useWebSocket()
  const { incidents: restIncidents }          = useIncidents({ status: 'OPEN' })
  const [pipelines, setPipelines]             = useState<Pipeline[]>([])
  const [costData, setCostData]               = useState<CostPoint[]>([])
  const [faithData, setFaithData]             = useState<Array<{ date: string; faithfulness: number }>>([])

  const allIncidents = wsIncidents.length > 0 ? wsIncidents : restIncidents

  useEffect(() => {
    apiClient.get('/api/pipelines')
      .then((r) => setPipelines(r.data))
      .catch(() => {})
    // Phase 1: fetch cost + faithfulness trend from /api/pipelines/metrics
  }, [])

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">AIMO</h1>
          <p className="text-xs text-gray-500 mt-0.5">AI Incident Management &amp; Observability</p>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/incidents" className="text-xs text-gray-400 hover:text-white transition-colors">
            Incidents
          </Link>
          <Link to="/settings" className="text-xs text-gray-400 hover:text-white transition-colors">
            Settings
          </Link>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto">
        <KpiBar incidents={allIncidents} />
        <PipelineGrid pipelines={pipelines} />
        <IncidentFeedPanel incidents={allIncidents} connected={connected} />
        <div className="grid grid-cols-2 gap-6">
          <CostChart data={costData} />
          <FaithfulnessChart data={faithData} />
        </div>
      </main>
    </div>
  )
}
