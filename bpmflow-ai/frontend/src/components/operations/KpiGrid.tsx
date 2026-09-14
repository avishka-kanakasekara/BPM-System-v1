import type { KpiReport } from '../../types/api'
import { Alert } from '../ui/primitives'
import { durationLabel } from '../../lib/operations'

function cell(label: string, value: string) {
  return (
    <div>
      <dt className="text-xs uppercase text-slate-500">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  )
}

export default function KpiGrid({ kpis }: { kpis: KpiReport | null }) {
  if (!kpis) {
    return <p className="text-sm text-slate-500">No KPI report was returned.</p>
  }
  return (
    <div className="space-y-3">
      {kpis.insufficient_evidence ? (
        <Alert tone="warning">Insufficient evidence. KPI values below are what the backend returned, including zeros.</Alert>
      ) : null}
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {cell('Total processes (window)', String(kpis.total_processes ?? 0))}
        {cell('Completed', String(kpis.completed_processes ?? 0))}
        {cell('Exception processes', String(kpis.exception_processes ?? 0))}
        {cell('Active', String(kpis.active_processes ?? 0))}
        {cell('Completion rate', kpis.completion_rate == null ? '—' : String(kpis.completion_rate))}
        {cell('Exception rate', kpis.exception_rate == null ? '—' : String(kpis.exception_rate))}
        {cell('Avg completion time', durationLabel(kpis.average_completion_time_seconds))}
        {cell('Avg step duration', durationLabel(kpis.average_step_duration_seconds))}
        {cell('Avg human wait', durationLabel(kpis.average_human_wait_time_seconds))}
        {cell('Step success rate', kpis.workflow_step_success_rate == null ? '—' : String(kpis.workflow_step_success_rate))}
        {cell('Step failure rate', kpis.workflow_step_failure_rate == null ? '—' : String(kpis.workflow_step_failure_rate))}
        {cell('Total exceptions', String(kpis.total_exceptions ?? 0))}
      </dl>
    </div>
  )
}
