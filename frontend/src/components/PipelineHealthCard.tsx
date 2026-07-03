/**
 * PipelineHealthCard — GREEN / AMBER / RED health badge per pipeline.
 * Phase 1: derive status from open incident counts.
 */
interface Props {
  pipelineId: string
  pipelineName: string
  status: 'GREEN' | 'AMBER' | 'RED'
  openIncidents: number
}

const STATUS_STYLES: Record<string, string> = {
  GREEN: 'bg-green-900 text-green-400 border-green-800',
  AMBER: 'bg-amber-900 text-amber-400 border-amber-800',
  RED:   'bg-red-900 text-red-400 border-red-800',
}

export default function PipelineHealthCard({ pipelineId: _id, pipelineName, status, openIncidents }: Props) {
  return (
    <div className={`border rounded-lg p-4 ${STATUS_STYLES[status]}`}>
      <p className="text-xs font-mono truncate">{pipelineName}</p>
      <p className="text-lg font-bold mt-1">{status}</p>
      <p className="text-xs mt-0.5 opacity-70">{openIncidents} open</p>
    </div>
  )
}
