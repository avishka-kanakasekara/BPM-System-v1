import type { TimelineEvent } from '../../types/api'
import { EmptyState } from '../ui/primitives'
import { formatDateTime } from '../process-cockpit/helpers'
import { formatEventType } from '../../lib/operations'

export default function MonitoringTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return (
      <EmptyState
        title="No timeline events"
        body="Only backend-returned monitoring events are shown. Missing timestamps are not invented."
      />
    )
  }
  return (
    <ol className="space-y-0">
      {events.map((event, idx) => (
        <li key={`${event.event_type}-${event.timestamp}-${idx}`} className="flex gap-3">
          <div className="flex w-4 flex-col items-center">
            <span className="mt-1 h-2.5 w-2.5 rounded-full bg-slate-400" />
            {idx < events.length - 1 ? <span className="w-px flex-1 bg-slate-200" /> : null}
          </div>
          <div className="min-w-0 pb-4">
            <p className="text-sm font-medium">{formatEventType(event.event_type)}</p>
            <p className="text-xs text-slate-500">
              {event.timestamp ? formatDateTime(event.timestamp) : 'Timestamp unavailable'}
              {event.status ? ` · ${event.status}` : ''}
              {event.actor ? ` · ${event.actor}` : ''}
            </p>
            {event.evidence_ref ? (
              <p className="text-xs text-slate-500">Evidence: {event.evidence_ref}</p>
            ) : null}
          </div>
        </li>
      ))}
    </ol>
  )
}
