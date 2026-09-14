import { AGENT_BOUNDARIES } from '../../lib/agentBoundaries'
import { Panel } from '../ui/primitives'

export default function SupervisionLegend() {
  return (
    <Panel title="Human-supervised process">
      <p className="mb-3 text-sm text-slate-600">
        Stages advance through explicit actions. Nothing here runs the full workflow automatically.
      </p>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        {AGENT_BOUNDARIES.map((row) => (
          <div key={row.actor}>
            <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{row.actor}</dt>
            <dd className="mt-0.5 text-slate-700">{row.statement}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  )
}
