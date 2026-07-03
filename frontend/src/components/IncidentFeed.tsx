/**
 * IncidentFeed — real-time P0/P1 incident stream via WebSocket.
 * Phase 1: connect useWebSocket + render incident rows with severity badges.
 */
import type { Incident } from '../api/api'

interface Props {
  incidents: Incident[]
  connected: boolean
}

export default function IncidentFeed({ incidents, connected }: Props) {
  return (
    <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-200">Incident Feed</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full ${connected ? 'bg-green-900 text-green-400' : 'bg-gray-800 text-gray-500'}`}>
          {connected ? 'live' : 'connecting…'}
        </span>
      </div>
      {incidents.length === 0 ? (
        <p className="text-xs text-gray-600 py-8 text-center">No incidents — Phase 1 will populate this</p>
      ) : (
        <ul className="space-y-2">
          {incidents.map((inc) => (
            <li key={inc.id} className="text-xs text-gray-300 border-b border-gray-800 pb-2">
              [{inc.severity}] {inc.incident_type} — {inc.pipeline_name}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
