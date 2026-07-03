import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { apiClient } from '../api/api'
import type { Incident } from '../api/api'

const SEV_STYLES: Record<string, string> = {
  P0: 'bg-red-900/60 text-red-400 border border-red-700',
  P1: 'bg-orange-900/60 text-orange-400 border border-orange-700',
  P2: 'bg-yellow-900/60 text-yellow-400 border border-yellow-700',
  P3: 'bg-gray-800 text-gray-400 border border-gray-700',
}

interface TimelineEvent { event: string; timestamp: string; status?: string }

interface IncidentDetailData extends Incident {
  root_cause?: string
  suggested_fix?: string
  evidence?: Record<string, unknown>
  resolution_notes?: string
  resolved_at?: string
}

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>()
  const [incident, setIncident] = useState<IncidentDetailData | null>(null)
  const [timeline, setTimeline] = useState<TimelineEvent[]>([])
  const [loading, setLoading]   = useState(true)
  const [resolving, setResolving] = useState(false)
  const [notes, setNotes]         = useState('')
  const [falsePosCheck, setFalsePosCheck] = useState(false)

  useEffect(() => {
    if (!id) return
    Promise.all([
      apiClient.get(`/api/incidents/${id}`),
      apiClient.get(`/api/incidents/${id}/timeline`),
    ])
      .then(([incRes, tlRes]) => {
        setIncident(incRes.data)
        setTimeline(tlRes.data.events || [])
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  const handleResolve = async () => {
    if (!id || !notes.trim()) return
    setResolving(true)
    try {
      await apiClient.patch(`/api/incidents/${id}/resolve`, {
        resolution_notes: notes,
        false_positive: falsePosCheck,
      })
      setIncident((prev) => prev ? { ...prev, status: 'RESOLVED' } : prev)
    } catch {
      /* handled via global error boundary in Phase 1 */
    } finally {
      setResolving(false)
    }
  }

  if (loading) return <div className="min-h-screen bg-gray-950 text-gray-500 flex items-center justify-center">Loading…</div>
  if (!incident) return <div className="min-h-screen bg-gray-950 text-red-400 flex items-center justify-center">Incident not found</div>

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <Link to="/incidents" className="text-xs text-gray-500 hover:text-white">← Incidents</Link>
        <div className="mt-2 flex items-center gap-3">
          <span className={`text-xs px-2 py-0.5 rounded font-mono ${SEV_STYLES[incident.severity] || ''}`}>
            {incident.severity}
          </span>
          <span className="text-xs text-gray-500">{incident.incident_type}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded ml-auto ${
            incident.status === 'OPEN'         ? 'bg-red-900/40 text-red-400' :
            incident.status === 'ACKNOWLEDGED' ? 'bg-yellow-900/40 text-yellow-400' :
            'bg-green-900/40 text-green-400'}`}>
            {incident.status}
          </span>
        </div>
        <h1 className="text-lg font-bold mt-2">{incident.title}</h1>
        <p className="text-xs text-gray-500 mt-1">Pipeline: {incident.pipeline_name || incident.pipeline_id}</p>
      </header>

      <main className="p-6 max-w-4xl mx-auto space-y-6">

        {/* Timeline */}
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Timeline</h2>
          <div className="space-y-2">
            {timeline.map((ev, i) => (
              <div key={i} className="flex items-center gap-3 text-xs">
                <span className="text-gray-600 font-mono w-32 flex-shrink-0">{new Date(ev.timestamp).toLocaleString()}</span>
                <span className="w-2 h-2 rounded-full bg-indigo-500 flex-shrink-0" />
                <span className="text-gray-400">{ev.event}{ev.status ? ` → ${ev.status}` : ''}</span>
              </div>
            ))}
          </div>
        </section>

        {/* Root Cause */}
        {incident.root_cause && (
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Root Cause (AI Generated)</h2>
            <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{incident.root_cause}</p>
          </section>
        )}

        {/* Evidence */}
        {incident.evidence && (
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Evidence</h2>
            <pre className="text-xs text-gray-400 overflow-x-auto">{JSON.stringify(incident.evidence, null, 2)}</pre>
          </section>
        )}

        {/* Suggested Fix */}
        {incident.suggested_fix && (
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Suggested Fix</h2>
            <pre className="text-xs text-green-400 bg-gray-950 p-3 rounded overflow-x-auto">{incident.suggested_fix}</pre>
          </section>
        )}

        {/* Resolve */}
        {incident.status !== 'RESOLVED' && (
          <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-3">Resolve Incident</h2>
            <textarea
              value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Add resolution notes…"
              className="w-full bg-gray-950 border border-gray-700 text-sm text-gray-300 rounded p-2 h-24 resize-none"
            />
            <div className="flex items-center gap-3 mt-2">
              <label className="flex items-center gap-2 text-xs text-gray-400">
                <input type="checkbox" checked={falsePosCheck} onChange={(e) => setFalsePosCheck(e.target.checked)} />
                Mark as false positive
              </label>
              <button
                onClick={handleResolve}
                disabled={resolving || !notes.trim()}
                className="ml-auto px-4 py-1.5 text-xs font-medium bg-green-700 hover:bg-green-600 disabled:opacity-40 rounded transition-colors">
                {resolving ? 'Resolving…' : 'Mark Resolved'}
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
