import { FormEvent, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert, PageHeader, Panel, controlClassName } from '../components/ui/primitives'

export default function SignInPage() {
  const { session, signIn, loading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from =
    (location.state as { from?: string } | null)?.from &&
    !(location.state as { from?: string }).from?.startsWith('/sign-')
      ? (location.state as { from: string }).from
      : '/'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && session) return <Navigate to={from} replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await signIn(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      const msg = (err as Error).message || 'Sign-in failed'
      if (/invalid login credentials/i.test(msg)) {
        setError('Invalid email or password. Sign up first, or confirm your email if required.')
      } else if (/email not confirmed/i.test(msg)) {
        setError(
          'Email not confirmed. Check your inbox, or ask an administrator to confirm your account.',
        )
      } else {
        setError(msg)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <PageHeader
        title="Sign in"
        description="Access your BPMFlow AI workspace to manage processes with AI assistance and human oversight."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      <Panel>
        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-base-content">Email</span>
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={controlClassName}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-base-content">Password</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={controlClassName}
            />
          </label>
          <button type="submit" disabled={submitting} className="btn btn-primary w-full">
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-base-content/70">
          Need an account?{' '}
          <Link to="/sign-up" className="font-medium text-base-content underline-offset-2 hover:underline">
            Sign up
          </Link>
        </p>
      </Panel>
    </div>
  )
}
