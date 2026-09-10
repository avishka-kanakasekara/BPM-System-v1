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

  const warnings: string[] = []
  const missing = payload?.missing_or_contradictory_fields
  if (Array.isArray(missing)) {
    for (const item of missing) {
      if (typeof item === 'string' && item.trim()) warnings.push(item)
    }
  }
  const errors = payload?.discovery_errors
  if (Array.isArray(errors)) {
    for (const item of errors) {
      if (typeof item === 'string' && item.trim()) warnings.push(item)
    }
  }

  const confidence =
    typeof discovery?.overall_confidence === 'number'
      ? discovery.overall_confidence
      : typeof message?.overall_confidence === 'number'
        ? message.overall_confidence
        : null

  const status =
    discovery?.discovery_status ||
    message?.status ||
    null

  const processName =
    (typeof payload?.process_name === 'string' && payload.process_name) ||
    discovery?.name ||
    null

  return { activities, rules, dependencies, warnings, confidence, status, processName }
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
    <Panel title="Process Discovery">
      <p className="mb-4 text-sm text-base-content/70">
        Upload documents or other evidence that describe how this process works. BPMFlow AI extracts
        activities, rules, and dependencies from the evidence — it does not approve the process.
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
            <p className="text-sm font-medium text-base-content">Upload Process Evidence</p>
            <p className="mt-1 text-xs text-base-content/60">
              PDF, DOCX, or CSV · up to {DISCOVERY_MAX_UPLOAD_MB} MB each
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
              Browse Files
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
              title="Upload process evidence to begin discovery."
              body="Select one or more supported documents that describe this business process."
            />
          )}

          <button
            type="button"
            className="btn btn-primary btn-sm w-full sm:w-auto"
            disabled={uploading || files.length === 0 || Boolean(fieldError)}
            onClick={() => void onUpload()}
          >
            {uploading ? 'Analyzing process evidence…' : 'Discover Process'}
          </button>

          {uploading ? (
            <div className="rounded-lg border border-sky-200/80 bg-sky-50 px-4 py-3 text-sm text-sky-950">
              <Spinner label="Analyzing process evidence…" />
              <p className="mt-2 text-xs leading-relaxed text-sky-900/80">
                BPMFlow AI is extracting activities, rules, and process dependencies from your
                evidence.
              </p>
            </div>
          ) : null}
        </div>
      ) : null}

      {hasResults && !uploading ? (
        <div className={canUpload ? 'mt-6 border-t border-base-200 pt-6' : ''}>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-base-content">Discovery completed</p>
            {lists.status ? <Badge tone="accent">{String(lists.status)}</Badge> : null}
            {lists.confidence != null ? (
              <Badge tone="good">
                Confidence{' '}
                {Math.round(lists.confidence <= 1 ? lists.confidence * 100 : lists.confidence)}%
              </Badge>
            ) : null}
          </div>

          {lists.processName ? (
            <p className="mb-4 text-sm text-base-content/80">
              Process name: <span className="font-medium text-base-content">{lists.processName}</span>
            </p>
          ) : null}

          {lists.warnings.length > 0 ? (
            <Alert tone="warning">
              <p className="font-medium">Discovery warnings</p>
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
              Discovery information is not available yet.
            </p>
          ) : (
            <div className="space-y-5">
              {lists.activities.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-base-content/55">
                    Activities
                  </p>
                  <ol className="mt-2 space-y-2">
                    {lists.activities.map((a, i) => (
                      <li
                        key={`${String(a.name)}-${i}`}
                        className="rounded-lg border border-base-200 bg-base-200/30 px-3 py-2 text-sm"
                      >
                        <span className="font-medium text-base-content">
                          {i + 1}. {String(a.name || a.title || `Activity ${i + 1}`)}
                        </span>
                        {a.actor ? (
                          <span className="mt-0.5 block text-xs text-base-content/60">
                            Participant: {String(a.actor)}
                          </span>
                        ) : null}
                        {a.system ? (
                          <span className="block text-xs text-base-content/60">
                            System: {String(a.system)}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}

              {lists.rules.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-base-content/55">
                    Rules
                  </p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-base-content/80">
                    {lists.rules.map((r, i) => (
                      <li key={i}>{String(r.description || r.rule || JSON.stringify(r))}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {lists.dependencies.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-base-content/55">
                    Dependencies
                  </p>
                  <ul className="mt-2 space-y-1 text-sm text-base-content/80">
                    {lists.dependencies.map((d, i) => (
                      <li key={i} className="rounded-md bg-base-200/40 px-3 py-1.5">
                        {String(d.predecessor || '?')} → {String(d.successor || '?')}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {evidenceNames.length > 0 ? (
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-base-content/55">
                    Evidence
                  </p>
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
            <div className="mt-5">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={planningBusy || planningDisabled}
                onClick={onContinueToPlanning}
              >
                {planningBusy ? 'Planning Resources...' : 'Continue to Resource Planning'}
              </button>
              {planningDisabled ? (
                <p className="mt-2 text-xs text-amber-800">
                  Tenant context is required for resource planning.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      {!canUpload && !hasResults ? (
        <p className="text-sm text-base-content/60">
          Discovery information is not available yet.
        </p>
      ) : null}

      {!hideStandaloneLink ? (
        <p className="mt-5 text-xs text-base-content/45">
          Need a standalone upload tool?{' '}
          <Link to="/discover" className="underline underline-offset-2">
            Open Process Discovery
          </Link>
        </p>
      ) : null}
    </Panel>
  )
}
