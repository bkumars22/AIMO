import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Cell, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip } from 'recharts'
import { apiClient } from '../api/api'

interface PipelineData {
  id: string
  name: string
  health_score: number
  description?: string
  created_at?: string
}

interface RunRow {
  run_id: string
  timestamp: string
  cost_usd: number
  latency_ms: number
  faithfulness_score?: number
  incident_count: number
}

export default function PipelineDetail() {
  const { id } = useParams<{ id: string }>()
  const [pipeline, setPipeline]   = useState<PipelineData | null>(null)
  const [runs, setRuns]           = useState<RunRow[]>([])
  const [incidents, setIncidents] = useState<unknown[]>([])
  const [loading, setLoading]     = useState(true)

  useEffect(() => {
    if (!id) return
    Promise.all([
      apiClient.get(`/api/pipelines/${id}`),
      apiClient.get(`/api/pipelines/${id}/incidents?limit=10`),
    ])
      .then(([pRes, iRes]) => {
        setPipeline(pRes.data)
        setIncidents(iRes.data.items || [])
        setRuns([])  // Phase 1: fetch from /api/pipelines/{id}/metrics
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="min-h-screen bg-gray-950 text-gray-500 flex items-center justify-center">Loading…</div>
  if (!pipeline) return <div className="min-h-screen bg-gray-950 text-red-400 flex items-center justify-center">Pipeline not found</div>

  const healthColor = pipeline.health_score >= 80 ? '#22c55e' : pipeline.health_score >= 60 ? '#f59e0b' : '#ef4444'
  const gaugeData = [{ name: 'health', value: pipeline.health_score }]

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <Link to="/" className="text-xs text-gray-500 hover:text-white">← Dashboard</Link>
        <h1 className="text-lg font-bold mt-2">{pipeline.name}</h1>
        {pipeline.description && <p className="text-xs text-gray-500 mt-0.5">{pipeline.description}</p>}
      </header>

      <main className="p-6 max-w-6xl mx-auto">
        {/* Health gauge + stats row */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 col-span-1 flex flex-col items-center">
            <p className="text-xs text-gray-500 mb-2">Health Score</p>
            <ResponsiveContainer width="100%" height={120}>
              <RadialBarChart cx="50%" cy="80%" innerRadius="60%" outerRadius="90%"
                startAngle={180} endAngle={0} data={gaugeData}>
                <RadialBar dataKey="value" cornerRadius={4} fill={healthColor} background={{ fill: '#1f2937' }}>
                  <Cell fill={healthColor} />
                </RadialBar>
              </RadialBarChart>
            </ResponsiveContainer>
            <p className="text-3xl font-bold -mt-6" style={{ color: healthColor }}>{pipeline.health_score}</p>
          </div>

          {[
            { label: 'Open Incidents', value: incidents.length, color: 'text-red-400' },
            { label: 'Total Runs', value: '—', color: 'text-gray-300' },
            { label: 'Avg Cost / Run', value: '—', color: 'text-gray-300' },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex flex-col justify-center">
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`text-2xl font-bold mt-1 ${color}`}>{value}</p>
            </div>
          ))}
        </div>

        {/* Incident history */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 mb-6">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Recent Incidents</h2>
          {incidents.length === 0 ? (
            <p className="text-xs text-gray-600 py-4 text-center">No incidents recorded</p>
          ) : (
            <p className="text-xs text-gray-400">{incidents.length} incidents — see <Link to="/incidents" className="text-indigo-400 hover:underline">Incidents list</Link> for details</p>
          )}
        </div>

        {/* Run history placeholder */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-3">Run History</h2>
          <p className="text-xs text-gray-600 py-4 text-center">
            Phase 1 — per-node latency heatmap + run table coming soon
          </p>
        </div>
      </main>
    </div>
  )
}
