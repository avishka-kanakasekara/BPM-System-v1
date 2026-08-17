import { useState } from 'react';
import { useLocation, useParams } from 'react-router-dom';
import { Agent3StatusBadge } from '../components/Agent3StatusBadge';
import { getRecommendationNavigationResponse } from '../navigation/recommendationNavigation';
import { formatTimestampToLocal } from '../utils/timestamps';

export default function RecommendationResultPage() {
  const { recommendationId = '' } = useParams(); const location = useLocation();
  const [copyStatus, setCopyStatus] = useState('');
  const response = getRecommendationNavigationResponse(location.state, recommendationId);
  if (!response || response.recommendation_id !== recommendationId) return <main className="min-h-screen bg-slate-50 p-6"><section className="mx-auto max-w-3xl rounded-xl border border-slate-200 bg-white p-6"><h1 className="text-2xl font-bold text-slate-900">Recommendation summary unavailable</h1><p className="mt-3 text-slate-600">This page was opened without the short-lived submission result. Only summary retrieval is available, and the detailed GET-based view arrives in Phase 5D.</p><dl className="mt-5"><dt className="text-sm font-medium text-slate-500">Recommendation ID</dt><dd className="mt-1 break-all font-mono text-slate-900">{recommendationId}</dd></dl></section></main>;
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(response.correlation_id);
      setCopyStatus('Correlation ID copied.');
    } catch {
      setCopyStatus('Unable to copy the correlation ID. Select and copy it manually.');
    }
  };
  return <main className="min-h-screen bg-slate-50 p-6"><section className="mx-auto max-w-3xl rounded-xl border border-slate-200 bg-white p-6 shadow-sm"><p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Persisted Agent 3 result</p><h1 className="mt-1 text-2xl font-bold text-slate-900">Allocation recommendation</h1><div className="mt-4"><Agent3StatusBadge status={response.recommendation_status} /></div>
    <dl className="mt-6 grid gap-5 sm:grid-cols-2"><div><dt className="text-sm text-slate-500">Recommendation ID</dt><dd className="break-all font-mono text-sm">{response.recommendation_id}</dd></div><div><dt className="text-sm text-slate-500">Correlation ID</dt><dd className="break-all font-mono text-sm">{response.correlation_id}</dd><button type="button" onClick={copy} className="mt-2 rounded border border-indigo-600 px-3 py-1 text-sm font-medium text-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2">Copy correlation ID</button><p aria-live="polite" className="mt-2 text-sm text-slate-600">{copyStatus}</p></div><div><dt className="text-sm text-slate-500">Persisted</dt><dd>Yes (true)</dd></div><div><dt className="text-sm text-slate-500">Persisted at</dt><dd>{formatTimestampToLocal(response.persisted_at)}</dd></div><div><dt className="text-sm text-slate-500">Human approval required</dt><dd>{response.recommendation.requires_human_approval ? 'Yes' : 'No'}</dd></div>{response.recommendation_status === 'FAILED' && <div><dt className="text-sm text-slate-500">Technical failure</dt><dd className="font-medium text-red-700">Manual intervention required</dd></div>}</dl>
    <p className="mt-6 rounded-lg bg-violet-50 p-4 text-violet-800">Full recommendation presentation will be available in the detailed result view.</p></section></main>;
}
