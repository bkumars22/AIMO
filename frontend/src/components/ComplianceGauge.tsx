/**
 * ComplianceGauge — radial gauge showing current compliance % per pipeline.
 * Phase 1: fetch /ai/compliance/latest and render with Recharts RadialBarChart.
 */
interface Props {
  pipelineName: string
  compliancePct: number
}

export default function ComplianceGauge({ pipelineName, compliancePct }: Props) {
  const color = compliancePct >= 90 ? '#22c55e' : compliancePct >= 70 ? '#f59e0b' : '#ef4444'
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-center">
      <p className="text-xs text-gray-500 mb-2">{pipelineName}</p>
      <p className="text-3xl font-bold" style={{ color }}>
        {compliancePct}%
      </p>
      <p className="text-xs text-gray-600 mt-1">compliance</p>
    </div>
  )
}
