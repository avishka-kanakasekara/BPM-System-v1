import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../services/supabaseClient'
import { apiErrorMessage, getCurrentUser, type CurrentUser } from '../services/apiClient'

type SignUpResult = {
  needsEmailConfirmation: boolean
}

type AuthState = {
  session: Session | null
  user: CurrentUser | null
  loading: boolean
  error: string | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, fullName?: string) => Promise<SignUpResult>
  signOut: () => Promise<void>
  refreshProfile: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refreshProfile = useCallback(async () => {
    if (!supabase) {
      setUser(null)
      return
    }
    try {
      const profile = await getCurrentUser()
      setUser(profile)
      setError(null)
      // Backend may have just provisioned app_metadata.tenant_id in development.
      // Refresh the JWT so Agent 3 session helpers see the claim too.
      const metaTenant = (
        await supabase.auth.getSession()
      ).data.session?.user?.app_metadata?.tenant_id
      if (profile.tenant_id && !metaTenant) {
        await supabase.auth.refreshSession()
      }
    } catch (err) {
      setUser(null)
      setError(apiErrorMessage(err))
    }
  }, [])

  useEffect(() => {
    let mounted = true
    async function boot() {
      if (!supabase) {
        setLoading(false)
        setError('Supabase is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.')
        return
      }
      const { data } = await supabase.auth.getSession()
      if (!mounted) return
      setSession(data.session)
      if (data.session) {
        try {
          const profile = await getCurrentUser()
          if (mounted) setUser(profile)
        } catch (err) {
          if (mounted) setError(apiErrorMessage(err))
        }
      }
      if (mounted) setLoading(false)
    }
    void boot()

    if (!supabase) return () => {
      mounted = false
    }

    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      if (next) {
        void refreshProfile()
      } else {
        setUser(null)
      }
    })
    return () => {
      mounted = false
      sub.subscription.unsubscribe()
    }
  }, [refreshProfile])

  const signIn = useCallback(async (email: string, password: string) => {
    if (!supabase) throw new Error('Supabase is not configured')
    setError(null)
    const { error: signError } = await supabase.auth.signInWithPassword({ email, password })
    if (signError) {
      setError(signError.message)
      throw signError
    }
    await refreshProfile()
  }, [refreshProfile])

  const signUp = useCallback(
    async (email: string, password: string, fullName?: string): Promise<SignUpResult> => {
      if (!supabase) throw new Error('Supabase is not configured')
      setError(null)
      const { data, error: signError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: fullName?.trim() ? { full_name: fullName.trim() } : undefined,
        },
      })
      if (signError) {
        setError(signError.message)
        throw signError
      }
      const needsEmailConfirmation = Boolean(data.user) && !data.session
      if (data.session) {
        await refreshProfile()
      }
      return { needsEmailConfirmation }
    },
    [refreshProfile],
  )

  const signOut = useCallback(async () => {
    if (!supabase) return
    await supabase.auth.signOut()
    setUser(null)
    setSession(null)
  }, [])

  const value = useMemo(
    () => ({ session, user, loading, error, signIn, signUp, signOut, refreshProfile }),
    [session, user, loading, error, signIn, signUp, signOut, refreshProfile],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
