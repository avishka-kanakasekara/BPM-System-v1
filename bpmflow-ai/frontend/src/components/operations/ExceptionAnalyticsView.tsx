import type { ExceptionAnalytics } from '../../types/api'
import { EmptyState } from '../ui/primitives'

export default function ExceptionAnalyticsView({ data }: { data: ExceptionAnalytics | null | undefined }) {
  if (!data) {
    return <EmptyState title="No exception analytics" body="The backend did not return exception analytics for this process." />
  }
  const codes = Object.entries(data.exceptions_by_code || {})
  const steps = Object.entries(data.exceptions_by_workflow_step || {})
  const maxCode = Math.max(1, ...codes.map(([, n]) => n))
  return (
    <div className="space-y-4">
      <dl className="grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase text-slate-500">Total</dt>
          <dd className="text-lg font-semibold">{data.total_exceptions ?? 0}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Open</dt>
          <dd className="text-lg font-semibold">{data.open_exceptions ?? 0}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase text-slate-500">Resolved</dt>
          <dd className="text-lg font-semibold">{data.resolved_exceptions ?? 0}</dd>
        </div>
      </dl>
      <p className="text-sm text-slate-600">
        Most frequent: {data.most_frequent_exception || '—'}
        {data.exception_rate_per_process != null ? ` · rate ${data.exception_rate_per_process}` : ''}
      </p>
      {codes.length === 0 ? (
        <p className="text-sm text-slate-500">No exception type distribution was returned.</p>
      ) : (
        <div className="space-y-2">
          {codes.map(([code, count]) => (
            <div key={code}>
              <div className="flex justify-between text-xs">
                <span>{code}</span>
                <span>{count}</span>
              </div>
              <div className="h-2 overflow-hidden rounded bg-slate-100">
                <div className="h-full bg-rose-400" style={{ width: `${(count / maxCode) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
      {steps.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Workflow step</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {steps.map(([step, count]) => (
                <tr key={step}>
                  <td className="font-mono text-xs">{step}</td>
                  <td>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  )
}
