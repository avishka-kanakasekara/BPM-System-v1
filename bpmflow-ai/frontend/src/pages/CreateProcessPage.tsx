import { FormEvent, useId, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiErrorMessage, createProcess } from '../services/apiClient'
import { Alert, PageHeader, Panel } from '../components/ui/primitives'

/** Predefined options already used by the Processes UI; backend accepts free-form process_type. */
const PROCESS_TYPES = [
  { value: 'PROCUREMENT', label: 'Procurement' },
  { value: 'INVOICE', label: 'Invoice' },
  { value: 'GENERAL', label: 'General' },
] as const

type FieldErrors = {
  name?: string
  processType?: string
}

function createErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to create this process."
  if (status === 503) return 'The BPMFlow AI service is temporarily unavailable.'
  return apiErrorMessage(err)
}

const inputClass =
  'mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400'
const inputErrorClass = 'border-rose-300 focus:border-rose-400 focus-visible:outline-rose-400'
const textareaClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-400'

export default function CreateProcessPage() {
  const navigate = useNavigate()
  const formId = useId()
  const nameId = `${formId}-name`
  const typeId = `${formId}-type`
  const descId = `${formId}-description`
  const nameErrorId = `${formId}-name-error`
  const typeErrorId = `${formId}-type-error`
  const formErrorId = `${formId}-form-error`

  const [name, setName] = useState('')
  const [processType, setProcessType] = useState('')
  const [description, setDescription] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function validate(): FieldErrors {
    const next: FieldErrors = {}
    if (!name.trim()) {
      next.name = 'Process name is required.'
    }
    if (!processType.trim()) {
      next.processType = 'Process type is required.'
    }
    return next
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (submitting) return

    setFormError(null)
    setSuccess(null)
    const errors = validate()
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return

    setSubmitting(true)
    try {
      const created = await createProcess({
        name: name.trim(),
        process_type: processType.trim(),
        description: description.trim() || undefined,
      })
      setSuccess(`“${created.name}” created as a draft. Opening process…`)
      navigate(`/processes/${created.id}`, { replace: true })
    } catch (err) {
      setFormError(createErrorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <div>
        <Link
          to="/processes"
          className="text-sm font-medium text-slate-500 transition-colors hover:text-slate-800"
        >
          ← Back to Processes
        </Link>
        <div className="mt-3">
          <PageHeader
            title="Create New Process"
            description="Start a new business process and define its basic information."
          />
        </div>
      </div>

      <Panel title="Basic Information">
        <p className="mb-5 text-sm text-slate-500">
          The process is created as a draft. Process Discovery starts later from the process detail
          page — not during creation.
        </p>

        {formError ? (
          <Alert tone="error">
            <div id={formErrorId} role="alert">
              {formError}
            </div>
          </Alert>
        ) : null}

        {success ? <Alert tone="success">{success}</Alert> : null}

        <form className="space-y-5" onSubmit={(e) => void onSubmit(e)} noValidate>
          <div>
            <label htmlFor={nameId} className="block text-sm font-medium text-slate-800">
              Process Name <span className="text-rose-600">*</span>
            </label>
            <p className="mt-0.5 text-xs text-slate-500">A clear name your team will recognize.</p>
            <input
              id={nameId}
              name="name"
              type="text"
              autoComplete="off"
              required
              aria-required="true"
              aria-invalid={Boolean(fieldErrors.name)}
              aria-describedby={fieldErrors.name ? nameErrorId : undefined}
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (fieldErrors.name) setFieldErrors((prev) => ({ ...prev, name: undefined }))
              }}
              placeholder="Purchase Approval Process"
              className={`${inputClass} ${fieldErrors.name ? inputErrorClass : ''}`}
              disabled={submitting}
            />
            {fieldErrors.name ? (
              <p id={nameErrorId} className="mt-1.5 text-sm text-rose-700" role="alert">
                {fieldErrors.name}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor={typeId} className="block text-sm font-medium text-slate-800">
              Process Type <span className="text-rose-600">*</span>
            </label>
            <p className="mt-0.5 text-xs text-slate-500">Category used to organize processes.</p>
            <select
              id={typeId}
              name="process_type"
              required
              aria-required="true"
              aria-invalid={Boolean(fieldErrors.processType)}
              aria-describedby={fieldErrors.processType ? typeErrorId : undefined}
              value={processType}
              onChange={(e) => {
                setProcessType(e.target.value)
                if (fieldErrors.processType) {
                  setFieldErrors((prev) => ({ ...prev, processType: undefined }))
                }
              }}
              className={`${inputClass} ${fieldErrors.processType ? inputErrorClass : ''}`}
              disabled={submitting}
            >
              <option value="" disabled>
                Select a process type
              </option>
              {PROCESS_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
            {fieldErrors.processType ? (
              <p id={typeErrorId} className="mt-1.5 text-sm text-rose-700" role="alert">
                {fieldErrors.processType}
              </p>
            ) : null}
          </div>

          <div>
            <label htmlFor={descId} className="block text-sm font-medium text-slate-800">
              Description <span className="font-normal text-slate-400">(optional)</span>
            </label>
            <p className="mt-0.5 text-xs text-slate-500">
              Brief context for reviewers and process owners.
            </p>
            <textarea
              id={descId}
              name="description"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Process for reviewing and approving purchase requests."
              className={textareaClass}
              disabled={submitting}
            />
          </div>

          <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
            <Link
              to="/processes"
              className={`btn btn-ghost btn-sm ${submitting ? 'pointer-events-none opacity-50' : ''}`}
              aria-disabled={submitting}
            >
              Cancel
            </Link>
            <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
              {submitting ? 'Creating Process...' : 'Create Process'}
            </button>
          </div>
        </form>
      </Panel>
    </div>
  )
}
