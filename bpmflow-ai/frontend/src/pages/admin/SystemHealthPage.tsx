import { useCallback, useEffect, useState } from 'react'
import { getDemoHealth, getHealth, type HealthStatus } from '../../services/apiClient'
import type { DemoHealthPayload } from '../../types/api'
import { Alert, PageHeader, Panel, Skeleton } from '../../components/ui/primitives'
import { operationsErrorMessage } from '../../lib/operations'

function flag(value: boolean | undefined): string {
  if (value == null) return 'Unavailable'
  return value ? 'Yes' : 'No'
}

function demoReadinessTone(
  health: HealthStatus,
  demo: DemoHealthPayload,
): 'success' | 'warning' | 'error' {
  if (health.status && health.status !== 'ok') return 'error'
  const gaps = demoReadinessGaps(health, demo)
  return gaps.length === 0 ? 'success' : 'warning'
}

function demoReadinessGaps(health: HealthStatus, demo: DemoHealthPayload): string[] {
  const gaps: string[] = []
  if (!health.status) gaps.push('backend status unavailable')
  else if (health.status !== 'ok') gaps.push(`backend status is ${health.status}`)
  if (!demo.database_url_configured) gaps.push('database URL not configured')
  if (!demo.supabase_url_configured) gaps.push('Supabase URL not configured')
  if (!demo.jwt_secret_configured) gaps.push('JWT secret not configured')
  if (!demo.migration_0024_on_disk) gaps.push('migration 0024 not on disk')
  if (!demo.tool_registry_allowlist_size) gaps.push('tool registry allowlist empty or unavailable')
  return gaps
}

function demoReadinessMessage(health: HealthStatus, demo: DemoHealthPayload): string {
  const gaps = demoReadinessGaps(health, demo)
  if (gaps.length === 0) {
    return `Demo readiness looks usable in ${demo.env} with persistence mode ${demo.persistence_mode}. Secrets are not displayed.`
  }
  return `Demo may not be fully ready: ${gaps.join('; ')}.`
}

export default function SystemHealthPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [demo, setDemo] = useState<DemoHealthPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [h, d] = await Promise.all([getHealth(), getDemoHealth()])
      setHealth(h)
      setDemo(d)
    } catch (err) {
      setError(operationsErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return (
    <div className="space-y-6">
      <PageHeader
        title="System health"
        description="Safe readiness flags from GET /health and GET /health/demo. Secrets, tokens, and credentials are not displayed."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {loading ? (
        <div aria-busy="true">
          <Skeleton className="h-40 w-full" />
        </div>
      ) : (
        <>
          {health && demo ? (
            <Alert tone={demoReadinessTone(health, demo)}>
              {demoReadinessMessage(health, demo)}
            </Alert>
          ) : null}
          <Panel title="Backend health">
            {!health ? (
              <p className="text-sm text-slate-500">Health payload unavailable.</p>
            ) : (
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase text-slate-500">Status</dt>
                  <dd>{health.status}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Environment</dt>
                  <dd>{health.env || 'Unavailable'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Database</dt>
                  <dd>{health.database || 'Unavailable'}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Database URL configured</dt>
                  <dd>{flag(health.database_url_configured)}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-slate-500">Supabase</dt>
                  <dd>{health.supabase || 'Unavailable'}</dd>
                </div>
              </dl>
            )}
          </Panel>
          <Panel title="Demo readiness">
            {!demo ? (
              <Alert tone="warning">Demo seed/configuration payload is unavailable.</Alert>
            ) : (
              <>
                {demo.note ? <Alert tone="info">{demo.note}</Alert> : null}
                <dl className="grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Environment</dt>
                    <dd>{demo.env}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Persistence mode</dt>
                    <dd>{demo.persistence_mode}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Mock LLM</dt>
                    <dd>{flag(demo.mock_llm)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Gemini offline</dt>
                    <dd>{flag(demo.gemini_offline)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Email dry run</dt>
                    <dd>{flag(demo.email_dry_run)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Supabase URL configured</dt>
                    <dd>{flag(demo.supabase_url_configured)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">JWT secret configured</dt>
                    <dd>{flag(demo.jwt_secret_configured)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Database URL configured</dt>
                    <dd>{flag(demo.database_url_configured)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Gemini configured</dt>
                    <dd>{flag(demo.gemini_configured)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Tool allowlist size</dt>
                    <dd>{demo.tool_registry_allowlist_size}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">Migration 0024 on disk</dt>
                    <dd>{flag(demo.migration_0024_on_disk)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-slate-500">SQL files on disk</dt>
                    <dd>{demo.migrations_on_disk?.length ?? 0}</dd>
                  </div>
                </dl>
              </>
            )}
          </Panel>
        </>
      )}
    </div>
  )
}
