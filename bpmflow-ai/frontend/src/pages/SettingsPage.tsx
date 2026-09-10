import { useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import {
  Alert,
  Badge,
  PageHeader,
  Panel,
} from '../components/ui/primitives'
import {
  applyAppearance,
  getStoredAppearance,
  setAppearancePreference,
  type AppearancePreference,
} from '../lib/appearance'

function displayOrFallback(value: string | null | undefined): string {
  if (value == null || String(value).trim() === '') return 'Not provided'
  return String(value).trim()
}

function formatRoleLabel(role: string | null | undefined): string {
  const key = (role || '').toLowerCase()
  if (key === 'admin') return 'Administrator'
  if (key === 'approver') return 'Approver'
  if (key === 'requester') return 'Requester'
  if (!role) return 'Not provided'
  return role
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function roleBadgeTone(role: string | null | undefined): 'neutral' | 'accent' | 'warn' | 'good' {
  const key = (role || '').toLowerCase()
  if (key === 'admin') return 'accent'
  if (key === 'approver') return 'warn'
  if (key === 'requester') return 'neutral'
  return 'neutral'
}

function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-200/70 ${className}`} />
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900">{children}</dd>
    </div>
  )
}

export default function SettingsPage() {
  const { user, session, loading, error, signOut, refreshProfile } = useAuth()
  const navigate = useNavigate()
  const [appearance, setAppearance] = useState<AppearancePreference>(() => getStoredAppearance())
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [confirmSignOut, setConfirmSignOut] = useState(false)

  useEffect(() => {
    applyAppearance(appearance)
  }, [appearance])

  function onAppearanceChange(next: AppearancePreference) {
    setAppearance(next)
    setAppearancePreference(next)
  }

  async function onSignOut() {
    setSigningOut(true)
    setSignOutError(null)
    setConfirmSignOut(false)
    try {
      await signOut()
      navigate('/sign-in', { replace: true })
    } catch {
      setSignOutError('Unable to sign out right now. Please try again.')
    } finally {
      setSigningOut(false)
    }
  }

  async function onRetryProfile() {
    try {
      await refreshProfile()
    } catch {
      /* AuthContext stores error */
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <PageHeader
        title="Settings"
        description="Manage your profile and application preferences."
      />

      {!session && !loading ? (
        <Alert tone="info">
          You are not signed in.{' '}
          <Link to="/sign-in" className="font-medium underline underline-offset-2">
            Sign in
          </Link>{' '}
          to view your profile and account settings.
        </Alert>
      ) : null}

      {error && session ? (
        <Alert tone="error">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>Unable to load your profile information.</span>
            <button type="button" className="btn btn-ghost btn-xs" onClick={() => void onRetryProfile()}>
              Retry
            </button>
          </div>
        </Alert>
      ) : null}

      {signOutError ? <Alert tone="error">{signOutError}</Alert> : null}

      {/* Profile */}
      <Panel title="Profile">
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : user ? (
          <dl className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name">{displayOrFallback(user.full_name)}</Field>
            <Field label="Email">{displayOrFallback(user.email)}</Field>
            <Field label="Role">
              <Badge tone={roleBadgeTone(user.role)}>{formatRoleLabel(user.role)}</Badge>
            </Field>
            <Field label="Department">{displayOrFallback(user.department)}</Field>
            <Field label="Workspace">
              {user.tenant_id ? (
                <span className="break-all font-mono text-xs text-slate-700">{user.tenant_id}</span>
              ) : (
                'Not provided'
              )}
            </Field>
          </dl>
        ) : session ? (
          <p className="text-sm text-slate-500">
            Unable to load your profile information.
            <button
              type="button"
              className="btn btn-ghost btn-xs ml-2"
              onClick={() => void onRetryProfile()}
            >
              Retry
            </button>
          </p>
        ) : (
          <p className="text-sm text-slate-500">Sign in to view your profile.</p>
        )}
        <p className="mt-4 text-xs text-slate-500">
          Role and workspace are assigned by your organization and cannot be changed here.
        </p>
      </Panel>

      {/* Account */}
      <Panel title="Account">
        <dl className="grid gap-4 sm:grid-cols-2">
          <Field label="Authentication provider">Supabase</Field>
          <Field label="Account email">
            {displayOrFallback(user?.email || session?.user?.email)}
          </Field>
          <Field label="Session">
            {session ? (
              <Badge tone="good">Active</Badge>
            ) : (
              <Badge tone="neutral">Signed out</Badge>
            )}
          </Field>
        </dl>
      </Panel>

      {/* Appearance — DaisyUI themes already configured */}
      <Panel title="Appearance">
        <p className="mb-4 text-sm text-slate-600">
          Choose how BPMFlow AI looks on this device. Preference is saved locally.
        </p>
        <fieldset>
          <legend className="sr-only">Appearance</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {(
              [
                { value: 'light', label: 'Light', hint: 'Corporate light theme' },
                { value: 'dark', label: 'Dark', hint: 'Business dark theme' },
                { value: 'system', label: 'System', hint: 'Match device setting' },
              ] as const
            ).map((opt) => {
              const selected = appearance === opt.value
              return (
                <label
                  key={opt.value}
                  className={[
                    'cursor-pointer rounded-xl border px-4 py-3 transition-colors',
                    selected
                      ? 'border-slate-900 bg-slate-900/[0.03]'
                      : 'border-slate-200 hover:border-slate-300',
                  ].join(' ')}
                >
                  <input
                    type="radio"
                    name="appearance"
                    value={opt.value}
                    checked={selected}
                    onChange={() => onAppearanceChange(opt.value)}
                    className="sr-only"
                  />
                  <span className="block text-sm font-medium text-slate-900">{opt.label}</span>
                  <span className="mt-0.5 block text-xs text-slate-500">{opt.hint}</span>
                </label>
              )
            })}
          </div>
        </fieldset>
      </Panel>

      {/* Session / Sign out */}
      <Panel title="Session">
        {session ? (
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-slate-900">Sign out of BPMFlow AI</p>
              <p className="mt-1 text-sm text-slate-500">
                You can sign back in anytime with your account credentials.
              </p>
            </div>
            <button
              type="button"
              className="btn btn-outline btn-sm border-rose-300 text-rose-800 hover:bg-rose-50"
              disabled={signingOut}
              onClick={() => setConfirmSignOut(true)}
            >
              {signingOut ? 'Signing out…' : 'Sign out'}
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-slate-600">You are currently signed out.</p>
            <Link to="/sign-in" className="btn btn-primary btn-sm">
              Sign in
            </Link>
          </div>
        )}
      </Panel>

      {confirmSignOut ? (
        <div className="modal modal-open">
          <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="sign-out-title">
            <h3 id="sign-out-title" className="text-lg font-semibold text-slate-900">
              Sign out?
            </h3>
            <p className="mt-2 text-sm text-slate-600">
              You will need to sign in again to access your workspace.
            </p>
            <div className="modal-action">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                disabled={signingOut}
                onClick={() => setConfirmSignOut(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-sm border-rose-300 bg-rose-600 text-white hover:bg-rose-700"
                disabled={signingOut}
                onClick={() => void onSignOut()}
              >
                {signingOut ? 'Signing out…' : 'Sign out'}
              </button>
            </div>
          </div>
          <button
            type="button"
            className="modal-backdrop bg-slate-900/40"
            aria-label="Close"
            onClick={() => (signingOut ? undefined : setConfirmSignOut(false))}
          />
        </div>
      ) : null}
    </div>
  )
}
