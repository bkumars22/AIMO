/**
 * InjectionLog — recent prompt injection attempts with type + similarity score.
 * Phase 1: fetch /api/incidents?type=PROMPT_INJECTION&limit=20 and render.
 */
interface InjectionRow {
  id: string
  timestamp: string
  injection_type: string
  similarity: number | null
  pipeline_name: string
}

interface Props {
  rows: InjectionRow[]
}

export default function InjectionLog({ rows }: Props) {
  return (
    <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-gray-200 mb-3">Injection Attempts</h2>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-600 py-4 text-center">No recent injection attempts</p>
      ) : (
        <table className="w-full text-xs text-gray-400">
          <thead>
            <tr className="text-gray-600 border-b border-gray-800">
              <th className="text-left pb-2">Time</th>
              <th className="text-left pb-2">Type</th>
              <th className="text-left pb-2">Pipeline</th>
              <th className="text-right pb-2">Sim</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-gray-800">
                <td className="py-1 font-mono">{r.timestamp}</td>
                <td className="py-1 text-red-400">{r.injection_type}</td>
                <td className="py-1">{r.pipeline_name}</td>
                <td className="py-1 text-right">{r.similarity != null ? r.similarity.toFixed(2) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
