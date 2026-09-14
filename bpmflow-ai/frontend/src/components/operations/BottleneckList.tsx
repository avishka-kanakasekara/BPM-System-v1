import type { BottleneckCandidate } from '../../types/api'
import { EmptyState } from '../ui/primitives'
import { durationLabel } from '../../lib/operations'

export default function BottleneckList({ items }: { items: BottleneckCandidate[] }) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No bottlenecks"
        body="The backend did not return observed bottleneck candidates for this process."
      />
    )
  }
  return (
    <ul className="space-y-3">
      {items.map((item, idx) => (
        <li key={`${item.workflow_step_id || item.step}-${idx}`} className="rounded-lg border border-slate-200 p-3">
          <p className="text-xs uppercase text-slate-500">Observed bottleneck</p>
          <p className="font-medium">{item.step}</p>
          <p className="text-sm text-slate-600">
            {item.step_type || 'Step'} · duration {durationLabel(item.average_duration_seconds)} · wait{' '}
            {durationLabel(item.average_wait_seconds)}
          </p>
          <p className="text-xs text-slate-500">
            Failures {item.failure_count ?? 0} · exceptions {item.exception_count ?? 0}
          </p>
          {item.reason?.length ? (
            <ul className="mt-2 list-disc pl-4 text-sm text-slate-700">
              {item.reason.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-slate-500">Evidence unavailable</p>
          )}
          <p className="mt-2 text-xs text-slate-500">This is an observed bottleneck, not a TO-BE recommendation.</p>
        </li>
      ))}
    </ul>
  )
}
