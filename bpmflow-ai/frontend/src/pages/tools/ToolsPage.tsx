import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { disableRegistryTool, enableRegistryTool, listRegistryTools } from '../../services/apiClient'
import type { ToolRegistryRecord } from '../../types/api'
import { useAuth } from '../../auth/AuthContext'
import { Alert, Badge, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'

export default function ToolsPage() {
  const { user } = useAuth()
  const isAdmin = (user?.role || '').toLowerCase() === 'admin'
  const [rows, setRows] = useState<ToolRegistryRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setRows(await listRegistryTools())
    } catch (err) {
      setError(operationsErrorMessage(err))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  async function toggle(tool: ToolRegistryRecord) {
    const next = tool.enabled ? 'disable' : 'enable'
    if (!window.confirm(`${next === 'disable' ? 'Disable' : 'Enable'} tool ${tool.tool_name}? This does not execute the tool.`)) {
      return
    }
    setBusy(tool.id)
    setError(null)
    setNotice(null)
    try {
      const updated = next === 'disable' ? await disableRegistryTool(tool.id) : await enableRegistryTool(tool.id)
      setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)))
      setNotice(`Tool ${updated.tool_name} is now ${updated.enabled ? 'enabled' : 'disabled'}.`)
    } catch (err) {
      setError(operationsErrorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Tool Registry"
        description="Agent2 can execute only tools registered in the Tool Registry and allowed for the current Workflow Step."
      />
      <Alert tone="info">
        One request → one Workflow Step → one registered tool → one receipt. This page does not execute tools and does not
        offer a free-form Agent 2 launcher. Changing enabled state does not allow arbitrary code execution.
      </Alert>
      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}
      <Panel>
        {loading ? (
          <div aria-busy="true">
            <Skeleton className="h-24 w-full" />
          </div>
        ) : rows.length === 0 ? (
          <EmptyState title="No registered tools" body="The Tool Registry returned no tools for this tenant." />
        ) : (
          <ul className="space-y-3">
            {rows.map((tool) => (
              <li key={tool.id} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <Link className="link text-lg font-semibold" to={`/tools/${tool.id}`}>
                      {tool.display_name || tool.tool_name}
                    </Link>
                    <p className="text-sm text-slate-500">
                      {tool.tool_category} · {tool.action_code}
                    </p>
                  </div>
                  <Badge tone={tool.enabled ? 'good' : 'warn'}>{tool.enabled ? 'Enabled' : 'Disabled'}</Badge>
                </div>
                <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Implementation key</dt>
                    <dd className="font-mono text-xs">{tool.implementation_key}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Version</dt>
                    <dd>{tool.version || 'Unavailable'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Requires authorization</dt>
                    <dd>{tool.requires_authorization ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Allowed step types</dt>
                    <dd>{tool.allowed_step_types?.length ? tool.allowed_step_types.join(', ') : 'Unavailable'}</dd>
                  </div>
                </dl>
                {isAdmin ? (
                  <button type="button" className="btn btn-ghost btn-sm mt-3" disabled={busy !== null} onClick={() => void toggle(tool)}>
                    {tool.enabled ? 'Disable' : 'Enable'}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  )
}
