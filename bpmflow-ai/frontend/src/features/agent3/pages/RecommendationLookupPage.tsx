import { FormEvent, useEffect, useRef, useState } from 'react';
import { getRecommendationByCorrelationId, getRecommendationById } from '../api/agent3Api';
import type { Agent3ClientError } from '../api/normalizeAgent3Error';
import { RecommendationErrorState, RecommendationLoadingState, SummaryRecommendation } from '../components/RecommendationPresentation';
import { Agent3SectionNavigation } from '../components/Agent3SectionNavigation';
import type { RecommendationSummary } from '../types/agent3Api';
import { validateLookupId } from '../validation/lookupValidation';

type Method = 'recommendation' | 'correlation';
type LookupState = { kind: 'initial' } | { kind: 'loading' } | { kind: 'result'; value: RecommendationSummary } | { kind: 'error'; title: string; message: string; retryable: boolean };
const inputClass = 'mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-200';
const buttonClass = 'mt-3 rounded-md bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-60';

function normalizeLookupError(error: unknown): { title: string; message: string; retryable: boolean } {
  const value = error as Partial<Agent3ClientError>;
  if (value.kind === 'authentication') return { title: 'Authentication required', message: 'Your session is unavailable or expired. Sign in before searching.', retryable: false };
  if (value.kind === 'authorization') return { title: 'Access unavailable', message: 'You are not authorized to retrieve this recommendation.', retryable: false };
  if (value.kind === 'not_found') return { title: 'Recommendation unavailable', message: 'The recommendation was not found or is not available to this tenant.', retryable: false };
  if (value.kind === 'conflict') return { title: 'Lookup conflict', message: 'The lookup could not be completed because of a recommendation conflict.', retryable: false };
  if (value.kind === 'unavailable' || value.retryable) return { title: 'Service unavailable', message: 'The recommendation service is temporarily unavailable.', retryable: true };
  return { title: 'Lookup failed', message: 'The recommendation could not be retrieved safely.', retryable: false };
}

export default function RecommendationLookupPage() {
  const [recommendationId, setRecommendationId] = useState(''); const [correlationId, setCorrelationId] = useState('');
  const [errors, setErrors] = useState<Partial<Record<Method, string>>>({}); const [state, setState] = useState<LookupState>({ kind: 'initial' });
  const latest = useRef(0); const lastLookup = useRef<{ method: Method; id: string } | null>(null); const errorRef = useRef<HTMLElement>(null);
  useEffect(() => { if (state.kind === 'error') errorRef.current?.focus(); }, [state]);

  async function execute(method: Method, id: string) {
    const request = ++latest.current; lastLookup.current = { method, id }; setState({ kind: 'loading' });
    try { const value = method === 'recommendation' ? await getRecommendationById(id) : await getRecommendationByCorrelationId(id); if (request === latest.current) setState({ kind: 'result', value }); }
    catch (error) { if (request === latest.current) setState({ kind: 'error', ...normalizeLookupError(error) }); }
  }
  function submit(method: Method, event: FormEvent) { event.preventDefault(); const raw = method === 'recommendation' ? recommendationId : correlationId; const id = raw.trim(); const error = validateLookupId(id); setErrors((current) => ({ ...current, [method]: error ?? undefined })); if (!error) void execute(method, id); }
  const retry = state.kind === 'error' && state.retryable && lastLookup.current ? () => void execute(lastLookup.current!.method, lastLookup.current!.id) : undefined;
  return <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900"><div className="mx-auto max-w-5xl space-y-6"><Agent3SectionNavigation /><header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Agent 3</p><h1 className="text-3xl font-bold">Recommendation lookup</h1><p className="mt-2 text-slate-500">Retrieve a tenant-scoped summary by recommendation or correlation ID.</p></header>
    <div className="grid gap-5 md:grid-cols-2"><form onSubmit={(event) => submit('recommendation', event)} aria-busy={state.kind === 'loading'} className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold">By recommendation ID</h2><label htmlFor="recommendationLookupId" className="mt-4 block text-sm font-medium">Recommendation ID</label><input id="recommendationLookupId" value={recommendationId} onChange={(event) => setRecommendationId(event.target.value)} className={inputClass} aria-invalid={Boolean(errors.recommendation)} aria-describedby={errors.recommendation ? 'recommendationLookupError' : undefined} />{errors.recommendation && <p id="recommendationLookupError" className="mt-1 text-sm text-red-700">{errors.recommendation}</p>}<button disabled={state.kind === 'loading'} className={buttonClass}>Find recommendation</button></form>
      <form onSubmit={(event) => submit('correlation', event)} aria-busy={state.kind === 'loading'} className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="text-xl font-semibold">By correlation ID</h2><label htmlFor="correlationLookupId" className="mt-4 block text-sm font-medium">Correlation ID</label><input id="correlationLookupId" value={correlationId} onChange={(event) => setCorrelationId(event.target.value)} className={inputClass} aria-invalid={Boolean(errors.correlation)} aria-describedby={errors.correlation ? 'correlationLookupError' : undefined} />{errors.correlation && <p id="correlationLookupError" className="mt-1 text-sm text-red-700">{errors.correlation}</p>}<button disabled={state.kind === 'loading'} className={buttonClass}>Find by correlation</button></form></div>
    {state.kind === 'loading' && <RecommendationLoadingState />}{state.kind === 'error' && <RecommendationErrorState ref={errorRef} title={state.title} message={state.message} retry={retry} />}{state.kind === 'result' && <SummaryRecommendation summary={state.value} />}
  </div></main>;
}
