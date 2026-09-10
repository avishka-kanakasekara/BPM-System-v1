import { FormEvent, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { Alert, PageHeader, Panel, controlClassName } from '../components/ui/primitives'

export default function SignUpPage() {
  const { session, signUp, loading } = useAuth()
  const navigate = useNavigate()
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [info, setInfo] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && session) return <Navigate to="/" replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setInfo(null)

    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setSubmitting(true)
    try {
      const result = await signUp(email.trim(), password, fullName.trim() || undefined)
      if (result.needsEmailConfirmation) {
        setInfo('Account created. Check your email to confirm, then sign in.')
        return
      }
      navigate('/', { replace: true })
    } catch (err) {
      setError((err as Error).message || 'Sign-up failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <PageHeader
        title="Create account"
        description="Register for BPMFlow AI to create and supervise business processes in your workspace."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {info ? <Alert tone="success">{info}</Alert> : null}
      <Panel>
        <form className="space-y-4" onSubmit={onSubmit} noValidate>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-base-content">Full name</span>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoComplete="name"
              className={controlClassName}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-base-content">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              className={controlClassName}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-base-content">Password</span>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              className={controlClassName}
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1.5 block font-medium text-base-content">Confirm password</span>
            <input
              type="password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              autoComplete="new-password"
              className={controlClassName}
            />
          </label>
          <button type="submit" disabled={submitting} className="btn btn-primary w-full">
            {submitting ? 'Creating account…' : 'Sign up'}
          </button>
        </form>
        <p className="mt-5 text-center text-sm text-base-content/70">
          Already have an account?{' '}
          <Link to="/sign-in" className="font-medium text-base-content underline-offset-2 hover:underline">
            Sign in
          </Link>
        </p>
      </Panel>
    </div>
  )
}
