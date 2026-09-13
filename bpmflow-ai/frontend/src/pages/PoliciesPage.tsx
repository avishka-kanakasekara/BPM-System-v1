import { FormEvent, useCallback, useEffect, useState } from 'react'
import {
  activatePolicyVersion,
  archivePolicyVersion,
  apiErrorMessage,
  listPolicies,
  uploadPolicy,
  type CompanyPolicyRecord,
} from '../services/apiClient'
import { useAuth } from '../auth/AuthContext'
import AccessDenied from '../components/AccessDenied'
import { Alert, EmptyState, PageHeader, Panel } from '../components/ui/primitives'

const CATEGORIES = [
  'PROCUREMENT',
  'APPROVAL',
  'BUDGET',
  'AUTHORIZATION',
  'SLA',
  'SECURITY',
  'FINANCE',
  'GENERAL',
] as const

export default function PoliciesPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [policies, setPolicies] = useState<CompanyPolicyRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [name, setName] = useState('Procurement Policy')
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>('PROCUREMENT')
  const [versionLabel, setVersionLabel] = useState('2026.1')
  const [effectiveFrom, setEffectiveFrom] = useState('')
  const [effectiveTo, setEffectiveTo] = useState('')
  const [textContent, setTextContent] = useState(
    'Approval Limits\n\nPurchases above 1000000 LKR require Senior Management approval.\nA quotation is required for procurement requests.\nSegregation of duties: requester cannot approve.',
  )
  const [file, setFile] = useState<File | null>(null)

  const refresh = useCallback(async () => {
    if (!isAdmin) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const rows = await listPolicies()
      setPolicies(rows)
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [isAdmin])

  useEffect(() => {
    void refresh()
  }, [refresh])

  if (!isAdmin) {
    return (
      <AccessDenied message="You don't have permission to manage company policies." />
    )
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault()
    if (!user?.tenant_id) {
      setError('Tenant context is required to upload company policies.')
      return
    }
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await uploadPolicy({
        name,
        category,
        version_label: versionLabel,
        text_content: textContent,
        document_type: file?.name.split('.').pop() || 'txt',
        activate: true,
        file,
        effective_from: effectiveFrom || undefined,
        effective_to: effectiveTo || undefined,
      })
      setNotice('Policy uploaded and activated for this tenant.')
      await refresh()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function onActivate(policyId: string, versionId: string) {
    setBusy(true)
    setError(null)
    try {
      await activatePolicyVersion(policyId, versionId)
      setNotice('Policy version activated.')
      await refresh()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function onArchive(policyId: string, versionId: string) {
    setBusy(true)
    setError(null)
    try {
      await archivePolicyVersion(policyId, versionId)
      setNotice('Policy version archived.')
      await refresh()
    } catch (err) {
      setError(apiErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Company Policies"
        description="Tenant-scoped policy knowledge used by Agent 4 risk review. Active versions only."
      />

      {error ? <Alert tone="error">{error}</Alert> : null}
      {notice ? <Alert tone="success">{notice}</Alert> : null}

      <Panel title="Upload policy">
        <form className="space-y-4" onSubmit={(e) => void onUpload(e)}>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">Policy name</span>
              <input
                className="h-10 w-full rounded-lg border border-slate-200 px-3"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">Category</span>
              <select
                className="h-10 w-full rounded-lg border border-slate-200 px-3"
                value={category}
                onChange={(e) => setCategory(e.target.value as (typeof CATEGORIES)[number])}
              >
                {CATEGORIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">Version</span>
              <input
                className="h-10 w-full rounded-lg border border-slate-200 px-3"
                value={versionLabel}
                onChange={(e) => setVersionLabel(e.target.value)}
                required
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">Document file (optional)</span>
              <input
                type="file"
                accept=".pdf,.docx,.csv,.txt"
                className="block w-full text-sm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">Effective from</span>
              <input
                type="datetime-local"
                className="h-10 w-full rounded-lg border border-slate-200 px-3"
                value={effectiveFrom}
                onChange={(e) => setEffectiveFrom(e.target.value)}
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1.5 block font-medium text-slate-700">Effective to (optional)</span>
              <input
                type="datetime-local"
                className="h-10 w-full rounded-lg border border-slate-200 px-3"
                value={effectiveTo}
                onChange={(e) => setEffectiveTo(e.target.value)}
              />
            </label>
          </div>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-slate-700">Policy text</span>
            <textarea
              className="min-h-36 w-full rounded-lg border border-slate-200 px-3 py-2"
              value={textContent}
              onChange={(e) => setTextContent(e.target.value)}
            />
          </label>
          <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
            {busy ? 'Uploading…' : 'Upload & activate'}
          </button>
        </form>
      </Panel>

      <Panel title="Policies for this tenant">
        {loading ? (
          <p className="text-sm text-slate-500">Loading policies…</p>
        ) : policies.length === 0 ? (
          <EmptyState
            title="No policies yet"
            body="Upload an active company policy to drive Agent 4 risk thresholds."
          />
        ) : (
          <div className="space-y-4">
            {policies.map((policy) => (
              <article key={policy.id} className="rounded-lg border border-slate-200 p-4">
                <div>
                  <h3 className="text-base font-semibold text-slate-900">{policy.name}</h3>
                  <p className="text-sm text-slate-500">
                    {policy.category} · {policy.id}
                  </p>
                </div>
                <ul className="mt-3 space-y-2">
                  {policy.versions.map((version) => (
                    <li
                      key={version.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm"
                    >
                      <div>
                        <span className="font-medium">v{version.version_label}</span>
                        <span className="mx-2 text-slate-400">·</span>
                        <span>{version.status}</span>
                        <span className="mx-2 text-slate-400">·</span>
                        <span>{version.document_name}</span>
                        <span className="mx-2 text-slate-400">·</span>
                        <span>{version.rules.length} rules</span>
                      </div>
                      <div className="flex gap-2">
                        {version.status !== 'ACTIVE' ? (
                          <button
                            type="button"
                            className="btn btn-outline btn-xs"
                            disabled={busy}
                            onClick={() => void onActivate(policy.id, version.id)}
                          >
                            Activate
                          </button>
                        ) : null}
                        {version.status !== 'ARCHIVED' ? (
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs"
                            disabled={busy}
                            onClick={() => void onArchive(policy.id, version.id)}
                          >
                            Archive
                          </button>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}
