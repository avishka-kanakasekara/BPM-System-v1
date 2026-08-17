import { FormEvent, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { submitAllocationRequest } from '../api/agent3Api';
import type { Agent3ClientError } from '../api/normalizeAgent3Error';
import { getAgent3Session } from '../auth/agent3Session';
import { FormErrorSummary } from '../components/FormErrorSummary';
import { getProvidedWorkflowContext, recommendationLookupPath, recommendationPath } from '../navigation/recommendationNavigation';
import { createMessageMetadata, generateCorrelationId, generateWorkflowId } from '../utils/metadata';
import { emptyBudgetDraft, emptyHumanDraft, type AllocationMode, type BudgetDraft, type FieldErrors, type HumanDraft, validateBudgetDraft, validateHumanDraft } from '../validation/allocationValidation';

const inputClass = 'mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 shadow-sm focus:border-indigo-600 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-slate-100';
const labelClass = 'block text-sm font-medium text-slate-800';

function Field({ id, label, required, description, error, children }: { id: string; label: string; required?: boolean; description?: string; error?: string; children: React.ReactNode }) {
  return <div><label className={labelClass} htmlFor={id}>{label} {required ? <span className="text-red-600">(required)</span> : <span className="text-slate-500">(optional)</span>}</label>
    {description && <p id={`${id}-description`} className="mt-1 text-sm text-slate-500">{description}</p>}{children}
    {error && <p id={`${id}-error`} className="mt-1 text-sm text-red-700">{error}</p>}</div>;
}

function HumanFields({ value, onChange, errors, disabled }: { value: HumanDraft; onChange: (value: HumanDraft) => void; errors: FieldErrors; disabled: boolean }) {
  const field = (key: keyof HumanDraft, id: string, label: string, required = false, type = 'text', description?: string) => <Field id={id} label={label} required={required} description={description} error={errors[id]}>
    <input id={id} type={type} className={inputClass} value={value[key]} disabled={disabled} aria-invalid={Boolean(errors[id])} aria-describedby={[description && `${id}-description`, errors[id] && `${id}-error`].filter(Boolean).join(' ') || undefined} onChange={(event) => onChange({ ...value, [key]: event.target.value })} />
  </Field>;
  return <fieldset className="space-y-5 rounded-xl border border-slate-200 bg-white p-5"><legend className="px-2 text-lg font-semibold text-slate-900">Human requirement</legend>
    {field('requiredRoles', 'humanRequiredRoles', 'Required roles', false, 'text', 'Comma-separated. Exact duplicates are removed; order and case are preserved.')}
    {field('mandatorySkills', 'humanMandatorySkills', 'Mandatory skills', false, 'text', 'Comma-separated values.')}
    {field('preferredSkills', 'humanPreferredSkills', 'Preferred skills', false, 'text', 'Comma-separated values.')}
    {field('requiredAuthority', 'humanRequiredAuthority', 'Required authority')}
    {field('taskDeadline', 'humanTaskDeadline', 'Task deadline', true, 'datetime-local')}
    {field('estimatedEffortHours', 'humanEstimatedEffortHours', 'Estimated effort hours', true, 'text', 'Enter a non-negative decimal, for example 8.50.')}
    {field('processStage', 'humanProcessStage', 'Process stage', true)}
  </fieldset>;
}

function BudgetFields({ value, onChange, errors, disabled }: { value: BudgetDraft; onChange: (value: BudgetDraft) => void; errors: FieldErrors; disabled: boolean }) {
  const field = (key: keyof BudgetDraft, id: string, label: string, required = false, type = 'text', description?: string) => <Field id={id} label={label} required={required} description={description} error={errors[id]}>
    <input id={id} type={type} className={inputClass} value={value[key]} disabled={disabled} aria-invalid={Boolean(errors[id])} aria-describedby={[description && `${id}-description`, errors[id] && `${id}-error`].filter(Boolean).join(' ') || undefined} onChange={(event) => onChange({ ...value, [key]: event.target.value })} />
  </Field>;
  return <fieldset className="space-y-5 rounded-xl border border-slate-200 bg-white p-5"><legend className="px-2 text-lg font-semibold text-slate-900">Budget requirement</legend>
    {field('requiredAmount', 'budgetRequiredAmount', 'Required amount', true, 'text', 'Exact non-negative decimal value; no currency symbol.')}
    {field('currency', 'budgetCurrency', 'Currency', true, 'text', 'Enter the backend business currency value without an invented symbol.')}
    {field('costCentre', 'budgetCostCentre', 'Cost centre')}
    {field('taskDeadline', 'budgetTaskDeadline', 'Task deadline', true, 'datetime-local')}
    {field('processStage', 'budgetProcessStage', 'Process stage', true)}
  </fieldset>;
}

export default function AllocationRequestPage() {
  const location = useLocation(); const navigate = useNavigate();
  // Navigation state is browser-controlled. UUID validation establishes format only;
  // final production trust requires backend-provided or backend-verified workflow context.
  const workflow = useRef(getProvidedWorkflowContext(location.state));
  const correlationId = useRef(generateCorrelationId());
  const demoWorkflow = useRef({ processInstanceId: generateWorkflowId(), taskId: generateWorkflowId() });
  const pendingRef = useRef(false); const errorSummaryRef = useRef<HTMLDivElement>(null);
  const [sessionState, setSessionState] = useState<{ requesterId: string; tenantId: string } | null>(null);
  const [sessionStatus, setSessionStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [mode, setMode] = useState<AllocationMode>('HUMAN');
  const [human, setHuman] = useState(emptyHumanDraft); const [budget, setBudget] = useState(emptyBudgetDraft);
  const [errors, setErrors] = useState<FieldErrors>({}); const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<{ message: string; retryable: boolean; conflict?: boolean } | null>(null);

  useEffect(() => { let active = true; getAgent3Session().then(({ requesterId, tenantId }) => { if (active) { setSessionState({ requesterId, tenantId }); setSessionStatus('ready'); } }).catch(() => { if (active) setSessionStatus('error'); }); return () => { active = false; }; }, []);

  const invalid = (next: FieldErrors) => { setErrors(next); requestAnimationFrame(() => errorSummaryRef.current?.focus()); };
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!sessionState || pendingRef.current) return;
    const nextErrors: FieldErrors = {}; let humanValue = null; let budgetValue = null;
    if (mode !== 'BUDGET') { const result = validateHumanDraft(human, sessionState.requesterId); Object.assign(nextErrors, result.errors); humanValue = result.value; }
    if (mode !== 'HUMAN') { const result = validateBudgetDraft(budget, sessionState.requesterId); Object.assign(nextErrors, result.errors); budgetValue = result.value; }
    if (Object.keys(nextErrors).length) { invalid(nextErrors); return; }
    setErrors({}); setSubmitError(null); pendingRef.current = true; setSubmitting(true);
    const ids = workflow.current ?? demoWorkflow.current;
    try {
      const response = await submitAllocationRequest({ metadata: createMessageMetadata({ tenantId: sessionState.tenantId, correlationId: correlationId.current, processInstanceId: ids.processInstanceId, taskId: ids.taskId }), human_requirements: humanValue, budget_requirements: budgetValue });
      navigate(recommendationPath(response.recommendation_id), { state: { persistedResponse: response } });
    } catch (error) {
      const safe = error as Partial<Agent3ClientError>;
      if (safe.kind === 'authentication') setSubmitError({ message: 'Your authenticated session has expired. Sign in again before submitting.', retryable: false });
      else if (safe.kind === 'conflict') setSubmitError({ message: 'A recommendation may already exist for this correlation ID. Use recommendation lookup when Phase 5D is available.', retryable: false, conflict: true });
      else setSubmitError({ message: safe.retryable ? 'The service is temporarily unavailable. Review your draft and retry when ready.' : 'The allocation request could not be submitted safely.', retryable: Boolean(safe.retryable) });
    } finally { pendingRef.current = false; setSubmitting(false); }
  }

  if (sessionStatus === 'loading') return <main className="min-h-screen bg-slate-50 p-6"><p role="status" className="mx-auto max-w-3xl text-slate-600">Verifying authenticated session…</p></main>;
  if (sessionStatus === 'error' || !sessionState) return <main className="min-h-screen bg-slate-50 p-6"><section role="alert" className="mx-auto max-w-3xl rounded-xl border border-red-200 bg-white p-6"><h1 className="text-2xl font-bold text-slate-900">Authentication required</h1><p className="mt-2 text-slate-600">A valid managed session is required before an allocation request can be created.</p></section></main>;
  return <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900"><div className="mx-auto max-w-4xl space-y-6">
    <header><p className="text-sm font-semibold uppercase tracking-wide text-indigo-600">Agent 3</p><h1 className="mt-1 text-3xl font-bold">Create allocation request</h1><p className="mt-2 text-slate-500">Authenticated tenant context verified.</p><Link className="mt-2 inline-block text-indigo-700 underline focus:ring-2 focus:ring-indigo-500" to={recommendationLookupPath}>Look up a recommendation</Link>{!workflow.current && <p className="ml-3 mt-2 inline-flex rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-700">Standalone demo mode</p>}</header>
    <FormErrorSummary ref={errorSummaryRef} errors={errors} />
    {submitError && <section role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"><p>{submitError.message}</p>{(submitError.retryable || submitError.conflict) && <p className="mt-2 font-mono text-sm">Correlation ID: {correlationId.current}</p>}{submitError.retryable && <p className="mt-2 text-sm">Your correlation ID and draft have been preserved. Submit again when ready.</p>}</section>}
    <form onSubmit={submit} aria-busy={submitting} className="space-y-6">
      <fieldset disabled={submitting} className="rounded-xl border border-slate-200 bg-white p-5"><legend className="px-2 text-lg font-semibold">Allocation mode</legend><div className="grid gap-3 sm:grid-cols-3">{([['HUMAN','Human'],['BUDGET','Budget'],['MIXED','Human + Budget']] as const).map(([value,label]) => <label key={value} className={`flex cursor-pointer items-center rounded-lg border p-3 focus-within:ring-2 focus-within:ring-indigo-500 ${mode === value ? 'border-indigo-600 bg-indigo-50' : 'border-slate-200'}`}><input type="radio" name="allocation-mode" value={value} checked={mode === value} onChange={() => setMode(value)} className="mr-2" />{label}</label>)}</div></fieldset>
      {mode !== 'BUDGET' && <HumanFields value={human} onChange={setHuman} errors={errors} disabled={submitting} />}
      {mode !== 'HUMAN' && <BudgetFields value={budget} onChange={setBudget} errors={errors} disabled={submitting} />}
      <button type="submit" disabled={submitting} className="rounded-md bg-indigo-600 px-5 py-3 font-semibold text-white hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60">{submitting ? 'Submitting allocation…' : 'Submit allocation request'}</button>
      {submitting && <p role="status" className="text-sm text-slate-600">Securely submitting and persisting the allocation request…</p>}
    </form>
  </div></main>;
}
