import { useCallback, useId, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  apiErrorMessage,
  discoverProcess,
  type AgentMessage,
  type ProcessDetail,
} from '../../services/apiClient'
import { Alert, Badge, EmptyState, Panel, Spinner } from '../ui/primitives'

/** Matches backend ALLOWED_FILE_TYPES default (pdf,docx,csv) and MAX_UPLOAD_MB (20). */
export const DISCOVERY_ALLOWED_EXTENSIONS = ['pdf', 'docx', 'csv'] as const
export const DISCOVERY_MAX_UPLOAD_MB = 20
export const DISCOVERY_ACCEPT = '.pdf,.docx,.csv'

type Props = {
  processId: string
  /** Existing Agent 1 discovery record for this process, if any */
  discovery: ProcessDetail | null
  /** Latest discovery envelope from an upload in this session */
  latestMessage?: AgentMessage | null
  stage: string
  /** Called after upload/discovery succeeds (parent should refresh process + discovery) */
  onDiscoveryComplete?: (message: AgentMessage) => void | Promise<void>
  /** When true, show continue CTA to resource planning */
  showContinueToPlanning?: boolean
  onContinueToPlanning?: () => void
  planningBusy?: boolean
  planningDisabled?: boolean
  /** Hide deep-link to /discover (when already on that page) */
  hideStandaloneLink?: boolean
}

function discoveryErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  const detailText =
    typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message: unknown }).message)
        : ''

  if (status === 401) return 'Your session has expired. Please sign in again.'
  if (status === 403) return "You don't have permission to upload process evidence."
  if (status === 404) return 'The discovery service could not find the requested process.'
  if (status === 409) return 'This action is not available for the current process state.'
  if (status === 422 || status === 400) {
    return detailText || 'The uploaded evidence could not be processed. Check the file type and try again.'
  }
  if (status === 503 || status === 500) {
    if (/unavailable|llm|openai|gemini|timeout/i.test(detailText)) {
      return 'Process discovery is temporarily unavailable. Please try again later.'
    }
    return 'Process discovery could not be completed. Please try again later.'
  }
  if (/unavailable|AGENT_UNAVAILABLE/i.test(detailText || apiErrorMessage(err))) {
    return 'Process discovery is temporarily unavailable.'
  }
  return apiErrorMessage(err) || 'Process discovery could not be completed.'
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function fileExtension(name: string): string {
  const parts = name.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function confidenceLabel(confidence: number | null): string | null {
  if (confidence == null || Number.isNaN(confidence)) return null
  const pct = Math.round(confidence <= 1 ? confidence * 100 : confidence)
  if (pct >= 75) return `High confidence (${pct}%)`
  if (pct >= 45) return `Medium confidence (${pct}%)`
  return `Low confidence (${pct}%)`
}

function confidenceExplanation(confidence: number | null): string {
  if (confidence == null || Number.isNaN(confidence)) {
    return 'Confidence was not scored for this upload.'
  }
  const pct = Math.round(confidence <= 1 ? confidence * 100 : confidence)
  if (pct >= 75) {
    return `The evidence was clear enough to reconstruct most of the process with high confidence (${pct}%).`
  }
  if (pct >= 45) {
    return `The main path is visible, but some owners, systems, or timings are still uncertain (${pct}%).`
  }
  return `The evidence was thin or inconsistent, so treat this map as a draft that needs review (${pct}%).`
}

function formatDuration(value: unknown): string | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (value >= 24) return `${(value / 24).toFixed(1)} days`
    if (value >= 1) return `${value.toFixed(1)} hours`
    if (value > 0) return `${Math.round(value * 60)} minutes`
    return null
  }
  if (typeof value === 'string' && value.trim()) return value.trim()
  return null
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function stepPositionLabel(index: number, total: number): string {
  if (total <= 1) return 'Only step'
  if (index === 0) return 'Start of process'
  if (index === total - 1) return 'End of process'
  return `Middle step (${index + 1} of ${total})`
}

function humanStatus(status: string | null): string | null {
  if (!status) return null
  const key = status.toUpperCase()
  if (key === 'SUCCESS' || key === 'COMPLETED' || key === 'COMPLETE' || key === 'OK') {
    return 'Ready to review'
  }
  if (key === 'PARTIAL' || key === 'NEEDS_REVIEW') return 'Needs a quick review'
  if (key === 'FAILED' || key === 'ERROR') return 'Could not finish'
  return status
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function humanWarning(raw: string): string {
  const text = raw.trim()
  if (!text) return text
  if (/missing_or_contradictory|missing/i.test(text) && text.includes(':')) {
    return `Something was unclear or missing: ${text.split(':').slice(1).join(':').trim() || text}`
  }
  if (/^missing/i.test(text)) return `Missing detail: ${text.replace(/^missing[_ ]*/i, '')}`
  return text.replace(/_/g, ' ')
}

type StepInsight = {
  name: string
  actor: string | null
  system: string | null
  duration: string | null
  durationSource: 'measured' | 'estimated_text' | 'unavailable' | null
  durationNote: string | null
  occurrenceCount: number | null
  caseCount: number | null
  caseCoverage: number | null
  onMainPath: boolean
  isRework: boolean
  entryConditions: string[]
  exitConditions: string[]
  position: string
  completeness: number
  gaps: string[]
  predecessors: string[]
  successors: string[]
  rationale?: string | null
}

function buildStepInsights(
  activities: Array<Record<string, unknown>>,
  dependencies: Array<Record<string, unknown>>,
): StepInsight[] {
  return activities.map((a, i) => {
    const name = String(a.name || a.title || `Step ${i + 1}`)
    const actor = a.actor ? String(a.actor) : null
    const system = a.system ? String(a.system) : null
    const duration = formatDuration(a.avg_duration)
    const rawSource = typeof a.duration_source === 'string' ? a.duration_source : null
    const durationSource =
      rawSource === 'measured' || rawSource === 'estimated_text' || rawSource === 'unavailable'
        ? rawSource
        : duration
          ? 'measured'
          : 'unavailable'
    const durationNote = a.duration_note ? String(a.duration_note) : null
    const occurrenceCount =
      typeof a.occurrence_count === 'number' ? a.occurrence_count : null
    const caseCount = typeof a.case_count === 'number' ? a.case_count : null
    const caseCoverage =
      typeof a.case_coverage === 'number' ? a.case_coverage : null
    const onMainPath = a.on_main_path !== false
    const isRework = Boolean(a.is_rework)
    const entryConditions = asStringList(a.entry_conditions)
    const exitConditions = asStringList(a.exit_conditions)
    const gaps: string[] = []
    if (!actor) gaps.push('Owner not identified in the evidence')
    if (!system) gaps.push('Supporting system not identified')
    if (durationSource === 'unavailable') gaps.push('Timing not available from this upload')
    if (entryConditions.length === 0) gaps.push('Entry conditions not stated')
    if (exitConditions.length === 0) gaps.push('Exit conditions not stated')

    let completeness = 0
    if (actor) completeness += 1
    if (system) completeness += 1
    if (durationSource === 'measured' || durationSource === 'estimated_text') completeness += 1
    if (entryConditions.length > 0) completeness += 1
    if (exitConditions.length > 0) completeness += 1

    const predecessors = dependencies
      .filter((d) => String(d.successor || '') === name)
      .map((d) => String(d.predecessor || 'Previous step'))
    const successors = dependencies
      .filter((d) => String(d.predecessor || '') === name)
      .map((d) => String(d.successor || 'Next step'))

    return {
      name,
      actor,
      system,
      duration,
      durationSource,
      durationNote,
      occurrenceCount,
      caseCount,
      caseCoverage,
      onMainPath,
      isRework,
      entryConditions,
      exitConditions,
      position: stepPositionLabel(i, activities.length),
      completeness,
      gaps,
      predecessors,
      successors,
    }
  })
}

function buildFlowSummary(steps: StepInsight[], processName: string | null): string {
  if (steps.length === 0) return 'No process path could be reconstructed from the upload.'
  const first = steps[0]?.name
  const last = steps[steps.length - 1]?.name
  const labeled = processName ? `“${processName}”` : 'this process'
  if (steps.length === 1) {
    return `From the uploaded evidence, ${labeled} appears to center on a single step: ${first}.`
  }
  return `From the uploaded evidence, ${labeled} usually runs from “${first}” through ${steps.length} steps and ends at “${last}”.`
}

function extractLists(discovery: ProcessDetail | null, message: AgentMessage | null) {
  const json = asRecord(discovery?.process_json)
  const payload = asRecord(message?.payload) || json

  const activities: Array<Record<string, unknown>> = Array.isArray(payload?.activities)
    ? (payload!.activities as Array<Record<string, unknown>>)
    : Array.isArray(json?.activities)
      ? (json!.activities as Array<Record<string, unknown>>)
      : []

  const rules: Array<Record<string, unknown>> = Array.isArray(payload?.rules)
    ? (payload!.rules as Array<Record<string, unknown>>)
    : Array.isArray(json?.rules)
      ? (json!.rules as Array<Record<string, unknown>>)
      : []

  const dependencies: Array<Record<string, unknown>> = Array.isArray(payload?.dependencies)
    ? (payload!.dependencies as Array<Record<string, unknown>>)
    : Array.isArray(json?.dependencies)
      ? (json!.dependencies as Array<Record<string, unknown>>)
      : []

  const exceptions: Array<Record<string, unknown>> = Array.isArray(payload?.exceptions)
    ? (payload!.exceptions as Array<Record<string, unknown>>)
    : Array.isArray(json?.exceptions)
      ? (json!.exceptions as Array<Record<string, unknown>>)
      : []

  const warnings: string[] = []
  const missing = payload?.missing_or_contradictory_fields
  if (Array.isArray(missing)) {
    for (const item of missing) {
      if (typeof item === 'string' && item.trim()) warnings.push(humanWarning(item))
    }
  }
  const errors = payload?.discovery_errors
  if (Array.isArray(errors)) {
    for (const item of errors) {
      if (typeof item === 'string' && item.trim()) warnings.push(humanWarning(item))
    }
  }

  const confidence =
    typeof discovery?.overall_confidence === 'number'
      ? discovery.overall_confidence
      : typeof message?.overall_confidence === 'number'
        ? message.overall_confidence
        : null

  const confidenceBreakdown = asRecord(payload?.confidence) || asRecord(json?.confidence) || null
  const analytics = asRecord(payload?.analytics) || asRecord(json?.analytics) || null

  const status =
    discovery?.discovery_status ||
    message?.status ||
    null

  const processName =
    (typeof payload?.process_name === 'string' && payload.process_name) ||
    discovery?.name ||
    null

  const stepInsights = buildStepInsights(activities, dependencies)
  const selectionSummary =
    typeof analytics?.step_selection_summary === 'string'
      ? analytics.step_selection_summary
      : null
  const selectionSource =
    typeof analytics?.step_selection_source === 'string'
      ? analytics.step_selection_source
      : null
  const selectedRationales = Array.isArray(analytics?.selected_step_rationales)
    ? (analytics!.selected_step_rationales as Array<Record<string, unknown>>)
    : []
  const rationaleByName = new Map<string, string>()
  for (const item of selectedRationales) {
    const name = typeof item.name === 'string' ? item.name : ''
    const rationale = typeof item.rationale === 'string' ? item.rationale : ''
    if (name && rationale) rationaleByName.set(name.toLowerCase(), rationale)
  }
  const enrichedInsights = stepInsights.map((step) => ({
    ...step,
    rationale: rationaleByName.get(step.name.toLowerCase()) || null,
  }))

  return {
    activities,
    rules,
    dependencies,
    exceptions,
    warnings,
    confidence,
    confidenceBreakdown,
    analytics,
    status,
    processName,
    stepInsights: enrichedInsights,
    selectionSummary,
    selectionSource,
  }
}

export default function ProcessDiscoveryPanel({
  processId,
  discovery,
  latestMessage = null,
  stage,
  onDiscoveryComplete,
  showContinueToPlanning = false,
  onContinueToPlanning,
  planningBusy = false,
  planningDisabled = false,
  hideStandaloneLink = false,
}: Props) {
  const navigate = useNavigate()
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)
  const [sessionMessage, setSessionMessage] = useState<AgentMessage | null>(null)
  const [evidenceNames, setEvidenceNames] = useState<string[]>([])

  const message = sessionMessage || latestMessage
  const lists = useMemo(
    () => extractLists(discovery, message),
    [discovery, message],
  )
  const hasResults =
    lists.activities.length > 0 ||
    lists.rules.length > 0 ||
    lists.dependencies.length > 0 ||
    Boolean(discovery?.process_json && Object.keys(discovery.process_json).length > 0) ||
    Boolean(message)

  const canUpload = stage === 'DRAFT' || stage === 'DISCOVERING' || !hasResults

  const validateFiles = useCallback((next: File[]): string | null => {
    if (next.length === 0) return 'Select at least one file to upload.'
    const maxBytes = DISCOVERY_MAX_UPLOAD_MB * 1024 * 1024
    for (const file of next) {
      const ext = fileExtension(file.name)
      if (!DISCOVERY_ALLOWED_EXTENSIONS.includes(ext as (typeof DISCOVERY_ALLOWED_EXTENSIONS)[number])) {
        return `Unsupported file type for “${file.name}”. Allowed: PDF, DOCX, CSV.`
      }
      if (file.size > maxBytes) {
        return `“${file.name}” exceeds the ${DISCOVERY_MAX_UPLOAD_MB} MB limit.`
      }
    }
    return null
  }, [])

  function addFiles(list: FileList | File[] | null) {
    if (!list) return
    const incoming = Array.from(list)
    const merged = [...files]
    for (const file of incoming) {
      if (!merged.some((f) => f.name === file.name && f.size === file.size)) {
        merged.push(file)
      }
    }
    const validation = validateFiles(merged)
    setFieldError(validation)
    if (!validation) setError(null)
    setFiles(merged)
  }

  function removeFile(index: number) {
    const next = files.filter((_, i) => i !== index)
    setFiles(next)
    setFieldError(next.length ? validateFiles(next) : null)
  }

  async function onUpload() {
    const validation = validateFiles(files)
    if (validation) {
      setFieldError(validation)
      return
    }
    setUploading(true)
    setError(null)
    setFieldError(null)
    try {
      const uploadedNames = files.map((f) => f.name)
      const result = await discoverProcess(files, processId || undefined)
      setSessionMessage(result)
      setEvidenceNames(uploadedNames)
      setFiles([])
      await onDiscoveryComplete?.(result)

      // When discovery is attached to the open process, stay on this page.
      // Standalone /discover (empty processId) still navigates to the new process.
      if (result.process_id && !processId) {
        navigate(`/processes/${result.process_id}`, { replace: true })
      } else if (result.process_id && processId && result.process_id !== processId) {
        navigate(`/processes/${result.process_id}`, { replace: true })
      }
    } catch (err) {
      setError(discoveryErrorMessage(err))
    } finally {
      setUploading(false)
    }
  }

  return (
    <Panel title="Understand this process">
      <p className="mb-4 text-sm leading-relaxed text-base-content/70">
        Upload a file that shows how the work is done today. We read it and show you the steps in
        plain language. This does not approve spending or run the purchase — it only helps everyone
        agree on the process first.
      </p>

      {error ? <Alert tone="error">{error}</Alert> : null}

      {canUpload ? (
        <div className="space-y-4">
          <div
            className={[
              'rounded-xl border border-dashed px-4 py-8 text-center transition-colors',
              dragOver ? 'border-primary bg-primary/5' : 'border-base-300 bg-base-200/40',
              uploading ? 'pointer-events-none opacity-60' : '',
            ].join(' ')}
            onDragEnter={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={(e) => {
              e.preventDefault()
              setDragOver(false)
            }}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              addFiles(e.dataTransfer.files)
            }}
          >
            <p className="text-sm font-medium text-base-content">Drop files here or browse</p>
            <p className="mt-1 text-xs text-base-content/60">
              Best options: CSV process log, PDF guide, or Word document · up to{' '}
              {DISCOVERY_MAX_UPLOAD_MB} MB each
            </p>
            <input
              ref={inputRef}
              id={inputId}
              type="file"
              multiple
              accept={DISCOVERY_ACCEPT}
              className="sr-only"
              disabled={uploading}
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />
            <button
              type="button"
              className="btn btn-ghost btn-sm mt-4"
              disabled={uploading}
              onClick={() => inputRef.current?.click()}
            >
              Choose files
            </button>
          </div>

          {fieldError ? (
            <p className="text-sm text-rose-700" role="alert">
              {fieldError}
            </p>
          ) : null}

          {files.length > 0 ? (
            <ul className="space-y-2">
              {files.map((file, index) => (
                <li
                  key={`${file.name}-${file.size}-${index}`}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-base-200 bg-base-100 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-base-content">{file.name}</p>
                    <p className="text-xs text-base-content/55">
                      {fileExtension(file.name).toUpperCase() || 'FILE'} · {formatBytes(file.size)}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    disabled={uploading}
                    onClick={() => removeFile(index)}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              title="No files selected yet"
              body="Add at least one CSV, PDF, or DOCX that describes this process, then click Analyze."
            />
          )}

          <div className="space-y-2">
            <button
              type="button"
              className="btn btn-primary btn-sm w-full sm:w-auto"
              disabled={uploading || files.length === 0 || Boolean(fieldError)}
              onClick={() => void onUpload()}
            >
              {uploading ? 'Reading your files…' : 'Analyze files'}
            </button>
            <p className="text-xs text-base-content/55">
              Tip: a short CSV with columns like case_id, activity, and timestamp works well for a
              first test.
            </p>
          </div>

          {uploading ? (
            <div className="rounded-lg border border-sky-200/80 bg-sky-50 px-4 py-3 text-sm text-sky-950">
              <Spinner label="Reading your files…" />
              <p className="mt-2 text-xs leading-relaxed text-sky-900/80">
                Finding the steps, who is involved, and the order they usually happen in.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasResults && !uploading ? (
        <div className={canUpload ? 'mt-6 border-t border-base-200 pt-6' : ''}>
          <div className="mb-4 space-y-2">
            <p className="text-sm font-semibold text-base-content">What we learned</p>
            <div className="flex flex-wrap items-center gap-2">
              {humanStatus(lists.status) ? (
                <Badge tone="accent">{humanStatus(lists.status)}</Badge>
              ) : null}
              {confidenceLabel(lists.confidence) ? (
                <Badge tone="good">{confidenceLabel(lists.confidence)}</Badge>
              ) : null}
              <Badge tone="neutral">
                {lists.activities.length} step{lists.activities.length === 1 ? '' : 's'}
              </Badge>
            </div>
            {lists.processName ? (
              <p className="text-sm text-base-content/80">
                Looks like: <span className="font-medium text-base-content">{lists.processName}</span>
              </p>
            ) : null}
            <p className="rounded-md border border-amber-200/70 bg-amber-50/70 px-3 py-2 text-xs leading-relaxed text-amber-950/85">
              <span className="font-semibold">Human check:</span> This is AI reading of your upload,
              not a final process definition. Quickly compare the steps below with your original
              documents before you continue — especially owners, timing, and anything marked as a gap.
            </p>
          </div>

          {lists.warnings.length > 0 ? (
            <Alert tone="warning">
              <p className="font-medium">Please double-check these points</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm">
                {lists.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Alert>
          ) : null}

          {lists.activities.length === 0 &&
          lists.rules.length === 0 &&
          lists.dependencies.length === 0 ? (
            <p className="text-sm text-base-content/60">
              We could not find clear steps yet. Try another file or a CSV event log.
            </p>
          ) : (
            <div className="space-y-5">
              {lists.activities.length > 0 ? (
                <div className="space-y-4">
                  <div>
                    <p className="text-base font-semibold text-base-content">
                      Discovered process path
                    </p>
                    <p className="mt-1 text-sm leading-relaxed text-base-content/65">
                      {buildFlowSummary(lists.stepInsights, lists.processName)}
                    </p>
                    {lists.selectionSummary ? (
                      <p className="mt-2 rounded-md border border-sky-200/70 bg-sky-50/80 px-3 py-2 text-xs leading-relaxed text-sky-950/90">
                        <span className="font-semibold">Intelligent step selection:</span>{' '}
                        {lists.selectionSummary}
                        {lists.selectionSource ? (
                          <span className="text-sky-900/70"> ({lists.selectionSource})</span>
                        ) : null}
                      </p>
                    ) : null}
                  </div>

                  {/* Analysis summary strip */}
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {[
                      {
                        label: 'Steps found',
                        value: String(lists.stepInsights.length),
                        hint: 'Activities reconstructed from evidence',
                      },
                      {
                        label: 'Known owners',
                        value: `${lists.stepInsights.filter((s) => s.actor).length}/${lists.stepInsights.length}`,
                        hint: 'Steps with a clear person/role',
                      },
                      {
                        label: 'Timing coverage',
                        value: `${lists.stepInsights.filter((s) => s.durationSource === 'measured' || s.durationSource === 'estimated_text').length}/${lists.stepInsights.length}`,
                        hint:
                          lists.analytics?.fallback_mode === 'frequency_and_path'
                            ? 'Limited timestamps — using frequency fallback'
                            : 'Measured or text-estimated durations',
                      },
                      {
                        label: lists.analytics?.total_cases
                          ? 'Cases in log'
                          : 'Sequence links',
                        value: lists.analytics?.total_cases
                          ? String(lists.analytics.total_cases)
                          : String(lists.dependencies.length),
                        hint: lists.analytics?.total_cases
                          ? `${lists.analytics.total_events ?? 0} events analyzed`
                          : 'Before → after relationships',
                      },
                    ].map((stat) => (
                      <div
                        key={stat.label}
                        className="rounded-xl border border-base-300 bg-gradient-to-b from-base-100 to-base-200/60 px-3 py-3"
                      >
                        <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/50">
                          {stat.label}
                        </p>
                        <p className="mt-1 text-xl font-semibold tracking-tight text-base-content">
                          {stat.value}
                        </p>
                        <p className="mt-0.5 text-[11px] leading-snug text-base-content/55">
                          {stat.hint}
                        </p>
                      </div>
                    ))}
                  </div>

                  {lists.analytics?.fallback_mode === 'frequency_and_path' ? (
                    <Alert tone="info">
                      <p className="font-medium">Timing was limited in this upload</p>
                      <p className="mt-1 text-sm">
                        We could not measure wait times from timestamps for every step, so this
                        analysis emphasizes how often each step appears, whether it sits on the main
                        path, and any rework. Duration is only shown when measured or clearly stated
                        in the text.
                      </p>
                    </Alert>
                  ) : null}

                  <p className="text-xs leading-relaxed text-base-content/60">
                    {confidenceExplanation(lists.confidence)}
                    {lists.confidenceBreakdown ? (
                      <>
                        {' '}
                        Detail scores:{' '}
                        {Object.entries(lists.confidenceBreakdown)
                          .filter(([, v]) => typeof v === 'number')
                          .map(
                            ([k, v]) =>
                              `${k.replace(/_/g, ' ')} ${Math.round(Number(v) <= 1 ? Number(v) * 100 : Number(v))}%`,
                          )
                          .join(' · ')}
                        .
                      </>
                    ) : null}
                  </p>

                  {/* Rich step cards */}
                  <ol className="space-y-3">
                    {lists.stepInsights.map((step, i) => {
                      const coveragePct = Math.round((step.completeness / 5) * 100)
                      return (
                        <li
                          key={`${step.name}-${i}`}
                          className="overflow-hidden rounded-xl border border-base-300 bg-base-100 shadow-sm"
                        >
                          <div className="flex gap-0">
                            <div className="flex w-14 shrink-0 flex-col items-center justify-center bg-neutral px-2 py-4 text-neutral-content">
                              <span className="text-[10px] font-semibold uppercase tracking-wide opacity-70">
                                Step
                              </span>
                              <span className="text-2xl font-semibold leading-none">{i + 1}</span>
                            </div>
                            <div className="min-w-0 flex-1 px-4 py-3.5">
                              <div className="flex flex-wrap items-start justify-between gap-2">
                                <div className="min-w-0">
                                  <p className="text-base font-semibold text-base-content">
                                    {step.name}
                                  </p>
                                  <p className="mt-0.5 text-xs font-medium text-base-content/55">
                                    {step.position}
                                  </p>
                                  {step.rationale ? (
                                    <p className="mt-1.5 text-xs leading-relaxed text-base-content/70">
                                      Why selected: {step.rationale}
                                    </p>
                                  ) : null}
                                </div>
                                <div className="flex flex-wrap gap-1.5">
                                  <Badge tone={coveragePct >= 60 ? 'good' : coveragePct >= 40 ? 'warn' : 'neutral'}>
                                    Detail coverage {coveragePct}%
                                  </Badge>
                                  {step.onMainPath ? <Badge tone="accent">Main path</Badge> : null}
                                  {step.isRework ? <Badge tone="warn">Rework seen</Badge> : null}
                                  {step.gaps.length === 0 ? (
                                    <Badge tone="good">Fully described</Badge>
                                  ) : (
                                    <Badge tone="warn">{step.gaps.length} gap{step.gaps.length === 1 ? '' : 's'}</Badge>
                                  )}
                                </div>
                              </div>

                              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                <div className="rounded-lg bg-base-200/50 px-3 py-2">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                    Usually done by
                                  </p>
                                  <p className="mt-0.5 text-sm font-medium text-base-content">
                                    {step.actor || 'Not found in evidence'}
                                  </p>
                                </div>
                                <div className="rounded-lg bg-base-200/50 px-3 py-2">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                    System / tool
                                  </p>
                                  <p className="mt-0.5 text-sm font-medium text-base-content">
                                    {step.system || 'Not found in evidence'}
                                  </p>
                                </div>
                                <div className="rounded-lg bg-base-200/50 px-3 py-2">
                                  <div className="flex flex-wrap items-center justify-between gap-1">
                                    <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                      Duration
                                    </p>
                                    {step.durationSource === 'measured' ? (
                                      <Badge tone="good">Measured</Badge>
                                    ) : step.durationSource === 'estimated_text' ? (
                                      <Badge tone="warn">Estimated</Badge>
                                    ) : (
                                      <Badge tone="neutral">Not available</Badge>
                                    )}
                                  </div>
                                  <p className="mt-0.5 text-sm font-medium text-base-content">
                                    {step.duration || 'No measurable timing in this upload'}
                                  </p>
                                  <p className="mt-1 text-[11px] leading-snug text-base-content/55">
                                    {step.durationNote ||
                                      (step.durationSource === 'unavailable'
                                        ? 'Fallback analytics below use frequency and path position instead.'
                                        : null)}
                                  </p>
                                </div>
                                <div className="rounded-lg bg-base-200/50 px-3 py-2">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                    Frequency & coverage
                                  </p>
                                  <p className="mt-0.5 text-sm text-base-content">
                                    {step.occurrenceCount != null ? (
                                      <span>
                                        Seen <span className="font-medium">{step.occurrenceCount}</span> time
                                        {step.occurrenceCount === 1 ? '' : 's'}
                                      </span>
                                    ) : (
                                      <span className="text-base-content/60">Occurrence count unknown</span>
                                    )}
                                    {step.caseCount != null ? (
                                      <>
                                        <span className="mx-1.5 text-base-content/30">·</span>
                                        <span>
                                          in <span className="font-medium">{step.caseCount}</span> case
                                          {step.caseCount === 1 ? '' : 's'}
                                        </span>
                                      </>
                                    ) : null}
                                    {step.caseCoverage != null ? (
                                      <>
                                        <span className="mx-1.5 text-base-content/30">·</span>
                                        <span className="font-medium">
                                          {Math.round(step.caseCoverage * 100)}% of cases
                                        </span>
                                      </>
                                    ) : null}
                                  </p>
                                  <p className="mt-1 text-[11px] leading-snug text-base-content/55">
                                    Useful when timestamps are missing — shows how common this step is.
                                  </p>
                                </div>
                                <div className="rounded-lg bg-base-200/50 px-3 py-2 sm:col-span-2">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                    Flow connections
                                  </p>
                                  <p className="mt-0.5 text-sm text-base-content">
                                    {step.predecessors.length > 0 ? (
                                      <span>
                                        After: <span className="font-medium">{step.predecessors.join(', ')}</span>
                                      </span>
                                    ) : (
                                      <span className="text-base-content/60">No required previous step</span>
                                    )}
                                    <span className="mx-1.5 text-base-content/30">·</span>
                                    {step.successors.length > 0 ? (
                                      <span>
                                        Next: <span className="font-medium">{step.successors.join(', ')}</span>
                                      </span>
                                    ) : (
                                      <span className="text-base-content/60">No required next step</span>
                                    )}
                                  </p>
                                </div>
                              </div>

                              {(step.entryConditions.length > 0 || step.exitConditions.length > 0) && (
                                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                                  {step.entryConditions.length > 0 ? (
                                    <div>
                                      <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                        Before this step can start
                                      </p>
                                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-base-content/75">
                                        {step.entryConditions.map((c) => (
                                          <li key={c}>{c}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : null}
                                  {step.exitConditions.length > 0 ? (
                                    <div>
                                      <p className="text-[11px] font-semibold uppercase tracking-wide text-base-content/45">
                                        Done when
                                      </p>
                                      <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-base-content/75">
                                        {step.exitConditions.map((c) => (
                                          <li key={c}>{c}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : null}
                                </div>
                              )}

                              {step.gaps.length > 0 ? (
                                <div className="mt-3 rounded-lg border border-amber-200/80 bg-amber-50/80 px-3 py-2">
                                  <p className="text-[11px] font-semibold uppercase tracking-wide text-amber-900/70">
                                    Evidence gaps for this step
                                  </p>
                                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-amber-950/80">
                                    {step.gaps.map((g) => (
                                      <li key={g}>{g}</li>
                                    ))}
                                  </ul>
                                  <p className="mt-2 text-[11px] leading-snug text-amber-900/75">
                                    Hint: open the source document and confirm whether this detail is
                                    missing, unclear, or just worded differently — then update your
                                    evidence if needed.
                                  </p>
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </li>
                      )
                    })}
                  </ol>

                  {/* Analytical insights */}
                  <div className="rounded-xl border border-base-300 bg-base-200/40 px-4 py-4">
                    <p className="text-sm font-semibold text-base-content">Evidence analysis highlights</p>
                    <ul className="mt-2 space-y-2 text-sm text-base-content/80">
                      <li>
                        <span className="font-medium text-base-content">Timing source:</span>{' '}
                        {lists.stepInsights.filter((s) => s.durationSource === 'measured').length} measured
                        , {lists.stepInsights.filter((s) => s.durationSource === 'estimated_text').length}{' '}
                        text-estimated,{' '}
                        {lists.stepInsights.filter((s) => s.durationSource === 'unavailable').length} not
                        available
                        {lists.analytics?.fallback_mode === 'frequency_and_path'
                          ? ' — frequency and path coverage are used as the main fallback.'
                          : '.'}
                      </li>
                      <li>
                        <span className="font-medium text-base-content">Ownership coverage:</span>{' '}
                        {lists.stepInsights.filter((s) => s.actor).length} of{' '}
                        {lists.stepInsights.length} steps have a known owner
                        {lists.stepInsights.some((s) => !s.actor)
                          ? ` — review: ${lists.stepInsights
                              .filter((s) => !s.actor)
                              .map((s) => s.name)
                              .join(', ')}`
                          : '.'}
                      </li>
                      <li>
                        <span className="font-medium text-base-content">System coverage:</span>{' '}
                        {lists.stepInsights.filter((s) => s.system).length} of{' '}
                        {lists.stepInsights.length} steps mention a system or tool.
                      </li>
                      {lists.dependencies.length > 0 ? (
                        <li>
                          <span className="font-medium text-base-content">Critical sequence:</span>{' '}
                          {lists.dependencies
                            .slice(0, 3)
                            .map(
                              (d) =>
                                `“${String(d.predecessor || '?')}” before “${String(d.successor || '?')}”`,
                            )
                            .join('; ')}
                          {lists.dependencies.length > 3
                            ? ` (+${lists.dependencies.length - 3} more)`
                            : ''}
                          .
                        </li>
                      ) : (
                        <li>
                          <span className="font-medium text-base-content">Sequence:</span> No explicit
                          before/after links were extracted — order is inferred from the activity list.
                        </li>
                      )}
                      {lists.rules.length > 0 ? (
                        <li>
                          <span className="font-medium text-base-content">Controls found:</span>{' '}
                          {lists.rules.length} business rule
                          {lists.rules.length === 1 ? '' : 's'} detected from the documents.
                        </li>
                      ) : null}
                      {lists.warnings.length > 0 ? (
                        <li>
                          <span className="font-medium text-base-content">Data quality:</span>{' '}
                          {lists.warnings.length} unclear or missing field
                          {lists.warnings.length === 1 ? '' : 's'} need human review before you trust
                          automation.
                        </li>
                      ) : (
                        <li>
                          <span className="font-medium text-base-content">Data quality:</span> No major
                          missing-field warnings were reported for this upload.
                        </li>
                      )}
                    </ul>
                  </div>
                </div>
              ) : null}

              {lists.dependencies.length > 0 ? (
                <div>
                  <p className="text-sm font-medium text-base-content">What must happen first</p>
                  <p className="mt-0.5 text-xs text-base-content/55">
                    Each line means the left step should finish before the right step starts.
                  </p>
                  <ul className="mt-3 space-y-1.5 text-sm text-base-content/80">
                    {lists.dependencies.map((d, i) => (
                      <li key={i} className="rounded-md bg-base-200/40 px-3 py-2">
                        After <span className="font-medium">{String(d.predecessor || 'a step')}</span>
                        , then{' '}
                        <span className="font-medium">{String(d.successor || 'the next step')}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {lists.rules.length > 0 ? (
                <div>
                  <p className="text-sm font-medium text-base-content">Rules we noticed</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-base-content/80">
                    {lists.rules.map((r, i) => (
                      <li key={i}>
                        {String(r.description || r.rule || 'A process rule was detected.')}
                        {r.controls_activity ? (
                          <span className="text-base-content/55">
                            {' '}
                            (applies to {String(r.controls_activity)})
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {evidenceNames.length > 0 ? (
                <div>
                  <p className="text-sm font-medium text-base-content">Files we used</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-base-content/80">
                    {evidenceNames.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}

          {showContinueToPlanning && onContinueToPlanning ? (
            <div className="mt-5 space-y-2">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={planningBusy || planningDisabled}
                onClick={onContinueToPlanning}
              >
                {planningBusy ? 'Planning resources…' : 'Continue to resource planning'}
              </button>
              {planningDisabled ? (
                <p className="text-xs text-amber-800">
                  Sign in again if planning is blocked — your workspace context may be missing.
                </p>
              ) : (
                <p className="text-xs text-base-content/55">
                  Next we suggest people and budget. That is advice only, not an approval.
                </p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      {!canUpload && !hasResults ? (
        <p className="text-sm text-base-content/60">
          No discovery details yet for this process.
        </p>
      ) : null}

      {!hideStandaloneLink ? (
        <p className="mt-5 text-xs text-base-content/45">
          Prefer a dedicated upload page?{' '}
          <Link to="/discover" className="underline underline-offset-2">
            Open process discovery
          </Link>
        </p>
      ) : null}
    </Panel>
  )
}
