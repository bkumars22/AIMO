import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useIncidents } from '../hooks/useIncidents'
import type { Incident } from '../api/api'

const SEV_STYLES: Record<string, string> = {
  P0: 'bg-red-900/60 text-red-400 border border-red-700',
  P1: 'bg-orange-900/60 text-orange-400 border border-orange-700',
  P2: 'bg-yellow-900/60 text-yellow-400 border border-yellow-700',
  P3: 'bg-gray-800 text-gray-400 border border-gray-700',
}

const TYPE_ICON: Record<string, string> = {
  HALLUCINATION:       '🧠',
  COST_SPIKE:          '💰',
  COMPLIANCE_DRIFT:    '📋',
  LATENCY_DEGRADATION: '⏱',
  PROMPT_INJECTION:    '🛡',
  ANOMALY:             '⚠️',
}

function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function Incidents() {
  const [severity, setSeverity] = useState('')
  const [type,     setType]     = useState('')
  const [status,   setStatus]   = useState('')

  const { incidents, loading, error, refetch } = useIncidents({
    severity: severity || undefined,
    type:     type || undefined,
    status:   status || undefined,
  })

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div>
          <Link to="/" className="text-xs text-gray-500 hover:text-white mr-4">← Dashboard</Link>
          <span className="text-lg font-bold">Incidents</span>
        </div>
        <button onClick={refetch} className="text-xs text-gray-500 hover:text-white">↻ refresh</button>
      </header>

      {/* Filters */}
      <div className="border-b border-gray-800 px-6 py-3 flex items-center gap-4">
        <select
          value={severity} onChange={(e) => setSeverity(e.target.value)}
          className="bg-gray-900 border border-gray-700 text-xs text-gray-300 rounded px-2 py-1">
          <option value="">All severities</option>
          {['P0', 'P1', 'P2', 'P3'].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={type} onChange={(e) => setType(e.target.value)}
          className="bg-gray-900 border border-gray-700 text-xs text-gray-300 rounded px-2 py-1">
          <option value="">All types</option>
          {['HALLUCINATION', 'COST_SPIKE', 'COMPLIANCE_DRIFT', 'LATENCY_DEGRADATION', 'PROMPT_INJECTION'].map((t) =>
            <option key={t} value={t}>{t}</option>)}
        </select>

        <select
          value={status} onChange={(e) => setStatus(e.target.value)}
          className="bg-gray-900 border border-gray-700 text-xs text-gray-300 rounded px-2 py-1">
          <option value="">All statuses</option>
          {['OPEN', 'ACKNOWLEDGED', 'RESOLVED'].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <span className="text-xs text-gray-600 ml-auto">{incidents.length} incidents</span>
      </div>

      {/* Table */}
      <main className="p-6">
        {loading && <p className="text-gray-500 text-sm">Loading…</p>}
        {error   && <p className="text-red-400 text-sm">{error}</p>}

        {!loading && !error && incidents.length === 0 && (
          <div className="text-center py-24 text-gray-600">
            <p className="text-4xl mb-4">✓</p>
            <p className="text-sm">No incidents match the current filters</p>
          </div>
        )}

        {!loading && incidents.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-gray-800">
                  <th className="text-left pb-3 font-medium">Severity</th>
                  <th className="text-left pb-3 font-medium">Type</th>
                  <th className="text-left pb-3 font-medium">Title</th>
                  <th className="text-left pb-3 font-medium">Pipeline</th>
                  <th className="text-left pb-3 font-medium">Detected</th>
                  <th className="text-left pb-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {incidents.map((inc: Incident) => (
                  <tr key={inc.id} className="border-b border-gray-900 hover:bg-gray-900 transition-colors">
                    <td className="py-3 pr-3">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${SEV_STYLES[inc.severity] || ''}`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td className="py-3 pr-3 text-gray-400 text-xs">
                      {TYPE_ICON[inc.incident_type] || '⚠️'} {inc.incident_type}
                    </td>
                    <td className="py-3 pr-3 max-w-xs">
                      <Link to={`/incidents/${inc.id}`} className="text-gray-200 hover:text-indigo-400 transition-colors text-xs line-clamp-1">
                        {inc.title}
                      </Link>
                    </td>
                    <td className="py-3 pr-3 text-gray-500 text-xs font-mono">{inc.pipeline_name || '—'}</td>
                    <td className="py-3 pr-3 text-gray-500 text-xs">{inc.created_at ? formatTime(inc.created_at) : '—'}</td>
                    <td className="py-3 text-xs">
                      <span className={`px-1.5 py-0.5 rounded ${
                        inc.status === 'OPEN'         ? 'bg-red-900/40 text-red-400' :
                        inc.status === 'ACKNOWLEDGED' ? 'bg-yellow-900/40 text-yellow-400' :
                        'bg-green-900/40 text-green-400'}`}>
                        {inc.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  )
}
