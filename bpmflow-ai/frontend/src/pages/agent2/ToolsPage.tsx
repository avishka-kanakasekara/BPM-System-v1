import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  apiErrorMessage,
  executeAgent2Tool,
  listAgent2Tools,
  listProcesses,
  type Agent2ToolCapability,
  type ExecutionReceiptDetail,
} from '../../services/apiClient'
import {
  Alert,
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  Spinner,
  controlClassName,
} from '../../components/ui/primitives'

export default function Agent2ToolsPage() {
  const [tools, setTools] = useState<Agent2ToolCapability[]>([])
  const [processes, setProcesses] = useState<{ id: string; name: string; stage?: string }[]>([])
  const [selected, setSelected] = useState<Agent2ToolCapability | null>(null)
  const [processId, setProcessId] = useState('')
  const [taskId, setTaskId] = useState('')
  const [fields, setFields] = useState<Record<string, string>>({})
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [receipt, setReceipt] = useState<ExecutionReceiptDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    void Promise.all([listAgent2Tools(), listProcesses()])
      .then(([toolRows, procRows]) => {
        setTools(toolRows)
        setProcesses(
          procRows.map((p) => ({
            id: p.id,
            name: p.name,
            stage: p.current_stage,
          })),
        )
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  const grouped = useMemo(() => {
    const map = new Map<string, Agent2ToolCapability[]>()
    for (const t of tools) {
      const cat = t.category || 'General'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(t)
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [tools])

  function selectTool(tool: Agent2ToolCapability) {
    setSelected(tool)
    setReceipt(null)
    setError(null)
    const defaults: Record<string, string> = {}
    for (const f of tool.input_fields) {
      if (f.name === 'priority') defaults[f.name] = 'MEDIUM'
      else if (f.name === 'severity') defaults[f.name] = 'MEDIUM'
      else if (f.name === 'status') defaults[f.name] = 'IN_PROGRESS'
      else defaults[f.name] = ''
    }
    setFields(defaults)
  }

  const needsAuth = selected?.requires_agent4_authorization ?? true
  const proc = processes.find((p) => p.id === processId)
  const atExecution = (proc?.stage || '').toUpperCase() === 'WORKFLOW_EXECUTION'

  async function runTool() {
    if (!selected) return
    setExecuting(true)
    setError(null)
    try {
      const parameters: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(fields)) {
        if (v.trim() === '') continue
        if (k === 'amount' || k === 'elapsed_hours' || k === 'sla_hours' || k === 'delay_minutes') {
          parameters[k] = Number(v)
        } else if (k === 'limit') {
          parameters[k] = parseInt(v, 10)
        } else {
          parameters[k] = v
        }
      }
      const result = await executeAgent2Tool({
        process_id: processId,
        task_id: taskId || processId,
        tool_name: selected.name,
        parameters,
      })
      setReceipt(result)
      setConfirmOpen(false)
    } catch (err) {
      setError(apiErrorMessage(err))
      setConfirmOpen(false)
    } finally {
      setExecuting(false)
    }
  }

  const externalAction =
    selected &&
    ['send_email', 'send_reminder', 'request_quotation'].includes(selected.name)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agent 2 — Tools & actions"
        description="Every registered execution capability with real backend invocation and receipts."
        actions={
          <Link to="/agent2" className="text-sm text-indigo-600 hover:underline">
            ← Dashboard
          </Link>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {receipt ? (
        <Alert tone={receipt.status === 'SUCCESS' ? 'success' : 'error'}>
          Execution {receipt.status}.{' '}
          <Link to={`/agent2/executions/${receipt.execution_id || receipt.id}`} className="underline">
            View receipt
          </Link>
        </Alert>
      ) : null}

      {loading ? (
        <Spinner />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-1">
            {grouped.map(([category, items]) => (
              <Panel key={category} title={category}>
                <ul className="space-y-2">
                  {items.map((t) => (
                    <li key={t.name}>
                      <button
                        type="button"
                        onClick={() => selectTool(t)}
                        className={`w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                          selected?.name === t.name
                            ? 'border-indigo-400 bg-indigo-50'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <p className="font-medium">{t.name}</p>
                        <p className="text-xs text-slate-500 line-clamp-2">{t.description}</p>
                        <div className="mt-1 flex gap-1">
                          <Badge tone={t.available ? 'good' : 'bad'}>
                            {t.available ? 'Available' : 'Restricted'}
                          </Badge>
                          {t.read_only ? <Badge tone="neutral">Read-only</Badge> : null}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              </Panel>
            ))}
          </div>

          <div className="lg:col-span-2">
            {!selected ? (
              <EmptyState title="Select a tool" body="Choose a capability to configure and execute." />
            ) : (
              <Panel title={selected.name}>
                <p className="mb-4 text-sm text-slate-600">{selected.description}</p>
                <dl className="mb-4 grid grid-cols-2 gap-2 text-xs text-slate-500">
                  <div>
                    <dt>Category</dt>
                    <dd className="font-medium text-slate-800">{selected.category}</dd>
                  </div>
                  <div>
                    <dt>Agent 4 auth required</dt>
                    <dd className="font-medium text-slate-800">
                      {needsAuth ? 'Yes (WORKFLOW_EXECUTION)' : 'No'}
                    </dd>
                  </div>
                </dl>

                <div className="mb-4 grid gap-3 sm:grid-cols-2">
                  <label className="block text-sm">
                    Process
                    <select
                      value={processId}
                      onChange={(e) => setProcessId(e.target.value)}
                      className={`mt-1 ${controlClassName}`}
                    >
                      <option value="">Select process</option>
                      {processes.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.stage})
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block text-sm">
                    Task ID
                    <input
                      value={taskId}
                      onChange={(e) => setTaskId(e.target.value)}
                      placeholder="UUID (defaults to process id)"
                      className={`mt-1 ${controlClassName}`}
                    />
                  </label>
                </div>

                {needsAuth && processId && !atExecution ? (
                  <Alert tone="warning">
                    Process must be at WORKFLOW_EXECUTION after Agent 4 approval. Current:{' '}
                    {proc?.stage || 'unknown'}.
                  </Alert>
                ) : null}

                <div className="space-y-3">
                  {selected.input_fields.map((f) => (
                    <label key={f.name} className="block text-sm">
                      {f.name}
                      {f.required ? ' *' : ''}
                      <input
                        value={fields[f.name] ?? ''}
                        onChange={(e) =>
                          setFields((prev) => ({ ...prev, [f.name]: e.target.value }))
                        }
                        placeholder={f.description}
                        className={`mt-1 ${controlClassName}`}
                      />
                    </label>
                  ))}
                </div>

                <div className="mt-6 flex gap-2">
                  <button
                    type="button"
                    disabled={
                      !processId ||
                      executing ||
                      (needsAuth && !atExecution) ||
                      !selected.available
                    }
                    onClick={() =>
                      externalAction ? setConfirmOpen(true) : void runTool()
                    }
                    className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    {executing ? 'Executing…' : 'Execute tool'}
                  </button>
                </div>

                {confirmOpen ? (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm">
                    <p className="font-medium">Confirm external action</p>
                    <p className="mt-1 text-slate-700">
                      This will invoke <strong>{selected.name}</strong> via the real backend
                      provider. Continue?
                    </p>
                    <div className="mt-3 flex gap-2">
                      <button
                        type="button"
                        onClick={() => void runTool()}
                        className="rounded bg-indigo-600 px-3 py-1.5 text-white"
                      >
                        Confirm
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmOpen(false)}
                        className="rounded border px-3 py-1.5"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : null}
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
