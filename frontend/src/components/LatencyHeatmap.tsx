/**
 * LatencyHeatmap — per-node latency heatmap (node × time bucket).
 * Phase 1: fetch /ai/latency/heatmap and render with Recharts or d3-based grid.
 */
export default function LatencyHeatmap() {
  return (
    <section className="bg-gray-900 border border-gray-800 rounded-lg p-4">
      <h2 className="text-sm font-semibold text-gray-200 mb-3">Latency Heatmap</h2>
      <div className="flex items-center justify-center h-40 text-gray-600 text-xs">
        Phase 1 — per-node × time heatmap coming soon
      </div>
    </section>
  )
}
