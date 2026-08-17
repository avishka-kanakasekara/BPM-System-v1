import type { RecommendationStatus } from '../types/agent3Api';

const labels: Record<RecommendationStatus, string> = {
  GENERATED: 'Generated', PENDING_HUMAN_APPROVAL: 'Pending Human Approval', SUPERSEDED: 'Superseded',
  FAILED: 'Technical Failure / Manual Intervention Required',
};
const colors: Record<RecommendationStatus, string> = {
  GENERATED: 'bg-emerald-50 text-emerald-700', PENDING_HUMAN_APPROVAL: 'bg-amber-50 text-amber-700',
  SUPERSEDED: 'bg-slate-100 text-slate-700', FAILED: 'bg-red-50 text-red-700',
};
export function Agent3StatusBadge({ status }: { status: RecommendationStatus }) {
  return <span role="status" className={`inline-flex rounded-full px-3 py-1 text-sm font-semibold ${colors[status]}`}>{labels[status]}</span>;
}
