import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { EmptyState, PageHeader, Panel } from '../components/ui/primitives'

/**
 * My Tasks — human work queue.
 * No dedicated task inbox API exists yet; keep an honest limited-data state.
 */
export default function TasksPage() {
  const { user } = useAuth()

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Tasks"
        description="View work assigned to you across your business processes."
      />

      <Panel>
        <EmptyState
          title="Task management is not yet available for this workspace."
          body="BPMFlow AI stores workflow tasks internally, but a dedicated task inbox API is not exposed yet. Use Approvals and Exceptions for human decisions and recovery today."
          action={
            <>
              <Link to="/approvals" className="btn btn-primary btn-sm">
                Open Approvals
              </Link>
              <Link to="/exceptions" className="btn btn-ghost btn-sm">
                Open Exceptions
              </Link>
              <Link to="/processes" className="btn btn-ghost btn-sm">
                View Processes
              </Link>
            </>
          }
        />
        {user ? (
          <p className="mt-4 text-center text-xs text-base-content/50">
            Signed in as {user.full_name || user.email}
            {user.role ? ` · ${user.role}` : ''}
          </p>
        ) : null}
      </Panel>
    </div>
  )
}
