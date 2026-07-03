import { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../api/api'

export default function Settings() {
  const [slackUrl, setSlackUrl]   = useState('')
  const [saving, setSaving]       = useState(false)
  const [saved,  setSaved]        = useState(false)
  const [recalcing, setRecalcing] = useState(false)

  const handleSaveAlerts = async () => {
    setSaving(true)
    try {
      await apiClient.put('/api/alerts/settings', { slack_webhook_url: slackUrl })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      /* Phase 1: surface error */
    } finally {
      setSaving(false)
    }
  }

  const handleRecalculate = async (pipelineId: string) => {
    setRecalcing(true)
    try {
      await apiClient.post(`/api/pipelines/${pipelineId}/baseline/recalculate`)
    } catch {
      /* Phase 1: surface error */
    } finally {
      setRecalcing(false)
    }
  }

  const handleTestAlert = async () => {
    try {
      await apiClient.post('/api/alerts/test', { channel: 'slack' })
      alert('Test alert sent!')
    } catch {
      alert('Test alert failed — check your webhook URL')
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <Link to="/" className="text-xs text-gray-500 hover:text-white">← Dashboard</Link>
        <h1 className="text-lg font-bold mt-2">Settings</h1>
      </header>

      <main className="p-6 max-w-2xl mx-auto space-y-6">

        {/* Slack alert configuration */}
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Alert Configuration</h2>
          <label className="block text-xs text-gray-500 mb-1">Slack Webhook URL</label>
          <input
            type="url"
            value={slackUrl}
            onChange={(e) => setSlackUrl(e.target.value)}
            placeholder="https://hooks.slack.com/services/..."
            className="w-full bg-gray-950 border border-gray-700 text-sm text-gray-300 rounded px-3 py-2"
          />
          <div className="flex gap-3 mt-3">
            <button onClick={handleSaveAlerts} disabled={saving}
              className="px-4 py-1.5 text-xs font-medium bg-indigo-700 hover:bg-indigo-600 disabled:opacity-40 rounded transition-colors">
              {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save'}
            </button>
            <button onClick={handleTestAlert}
              className="px-4 py-1.5 text-xs font-medium bg-gray-700 hover:bg-gray-600 rounded transition-colors">
              Send Test Alert
            </button>
          </div>
        </section>

        {/* Baseline recalculation */}
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-2">Baseline Recalculation</h2>
          <p className="text-xs text-gray-500 mb-4">
            Use after a major pipeline change to reset anomaly detection baselines.
          </p>
          <button
            onClick={() => handleRecalculate('all')}
            disabled={recalcing}
            className="px-4 py-1.5 text-xs font-medium bg-amber-700 hover:bg-amber-600 disabled:opacity-40 rounded transition-colors">
            {recalcing ? 'Recalculating…' : 'Recalculate All Baselines'}
          </button>
        </section>

        {/* API key management */}
        <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-gray-300 mb-2">API Keys</h2>
          <p className="text-xs text-gray-500">
            API keys are generated when you register a pipeline via POST /pipelines/register.
            Each key is shown once — store it securely.
          </p>
          <p className="text-xs text-gray-600 mt-3">Phase 1: key rotation and revocation UI coming soon</p>
        </section>
      </main>
    </div>
  )
}
