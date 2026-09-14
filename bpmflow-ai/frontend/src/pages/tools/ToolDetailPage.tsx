import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getRegistryTool } from '../../services/apiClient'
import type { ToolRegistryRecord } from '../../types/api'
import { Alert, Badge, EmptyState, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'

export default function ToolDetailPage() {
  const { toolId = '' } = useParams()
  const [tool, setTool] = useState<ToolRegistryRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!toolId) return
    setLoading(true)
    setError(null)
    try {
      setTool(await getRegistryTool(toolId))
    } catch (err) {
      setTool(null)
      setError(operationsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [toolId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (loading && !tool) {
    return (
      <div aria-busy="true">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  if (!tool) {
    return (
      <div className="space-y-4">
        <Link to="/tools" className="text-sm font-medium text-slate-500">
          ← Tool Registry
        </Link>
        {error ? <Alert tone="error">{error}</Alert> : <EmptyState title="Tool not found" body="No Tool Registry record was returned." />}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/tools" className="text-sm font-medium text-slate-500">
        ← Tool Registry
      </Link>
      <PageHeader title={tool.display_name || tool.tool_name} description={tool.action_code} />
      <Alert tone="info">
        Agent2 can execute only tools registered in the Tool Registry and allowed for the current Workflow Step. This
        record is not an execution form.
      </Alert>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel title="Registration">
        <div className="mb-3">
          <Badge tone={tool.enabled ? 'good' : 'warn'}>{tool.enabled ? 'Enabled' : 'Disabled'}</Badge>
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase text-slate-500">Category</dt>
            <dd>{tool.tool_category}</dd>
          </div>
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
          <div>
            <dt className="text-xs uppercase text-slate-500">Permissions</dt>
            <dd>{tool.required_permissions?.length ? tool.required_permissions.join(', ') : 'Unavailable'}</dd>
          </div>
        </dl>
        {tool.description ? <p className="mt-3 text-sm text-slate-600">{tool.description}</p> : null}
      </Panel>
      <Panel title="Schemas">
        <p className="text-xs uppercase text-slate-500">Input schema</p>
        <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-3 text-xs">
          {tool.input_schema ? JSON.stringify(tool.input_schema, null, 2) : 'Unavailable'}
        </pre>
        <p className="mt-3 text-xs uppercase text-slate-500">Output schema</p>
        <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-3 text-xs">
          {tool.output_schema ? JSON.stringify(tool.output_schema, null, 2) : 'Unavailable'}
        </pre>
      </Panel>
    </div>
  )
}
