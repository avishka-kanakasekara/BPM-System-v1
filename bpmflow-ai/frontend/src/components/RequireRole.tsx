import type { ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'
import type { AppRole } from '../types/api'
import AccessDenied from './AccessDenied'
import { Skeleton } from './ui/primitives'

type RequireRoleProps = {
  roles: AppRole[]
  children: ReactNode
  message?: string
}

/** Route guard matching backend require_roles RBAC. */
export function RequireRole({ roles, children, message }: RequireRoleProps) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="space-y-4 py-6" aria-busy="true">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }

  const role = (user?.role || '').toLowerCase() as AppRole
  if (!user || !roles.includes(role)) {
    return (
      <AccessDenied
        message={
          message ||
          "You don't have permission to view this page. Contact an administrator if you need access."
        }
      />
    )
  }

  return <>{children}</>
}
