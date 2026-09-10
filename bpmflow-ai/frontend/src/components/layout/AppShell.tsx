import { useEffect, useId, useMemo, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'

type NavItem = { to: string; label: string; end?: boolean }

const PRIMARY_NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/processes', label: 'Processes' },
  { to: '/tasks', label: 'My Tasks' },
  { to: '/approvals', label: 'Approvals' },
  { to: '/exceptions', label: 'Exceptions' },
  { to: '/audit', label: 'Audit Trail' },
]

const SECONDARY_NAV: NavItem[] = [{ to: '/settings', label: 'Settings' }]

const PAGE_TITLES: Array<{ match: RegExp; title: string }> = [
  { match: /^\/$/, title: 'Dashboard' },
  { match: /^\/processes\/new/, title: 'Create Process' },
  { match: /^\/processes\/[^/]+/, title: 'Process detail' },
  { match: /^\/processes/, title: 'Processes' },
  { match: /^\/workflows\/[^/]+/, title: 'Process detail' },
  { match: /^\/workflows/, title: 'Processes' },
  { match: /^\/tasks/, title: 'My Tasks' },
  { match: /^\/approvals\/[^/]+/, title: 'Approval detail' },
  { match: /^\/approvals/, title: 'Approvals' },
  { match: /^\/exceptions\/[^/]+/, title: 'Exception detail' },
  { match: /^\/exceptions/, title: 'Exceptions' },
  { match: /^\/audit/, title: 'Audit Trail' },
  { match: /^\/settings/, title: 'Settings' },
  { match: /^\/sign-in/, title: 'Sign in' },
  { match: /^\/sign-up/, title: 'Sign up' },
  { match: /^\/discover/, title: 'Process Discovery' },
  { match: /^\/agent2\/kpis/, title: 'Process KPIs' },
  { match: /^\/agent2\/receipts/, title: 'Execution receipts' },
  { match: /^\/agent2\/recommendations/, title: 'Optimizations' },
  { match: /^\/agent3\/allocations/, title: 'Resource Planning' },
  { match: /^\/agent3\/recommendations/, title: 'Resource Recommendations' },
]

function pageTitleFor(pathname: string): string {
  for (const entry of PAGE_TITLES) {
    if (entry.match.test(pathname)) return entry.title
  }
  return 'BPMFlow AI'
}

function navClassName({ isActive }: { isActive: boolean }): string {
  return [
    'flex items-center rounded-lg px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-base-200 text-base-content'
      : 'text-base-content/70 hover:bg-base-200/70 hover:text-base-content',
  ].join(' ')
}

function formatRoleLabel(role: string | null | undefined): string {
  const key = (role || '').toLowerCase()
  if (key === 'admin') return 'Administrator'
  if (key === 'approver') return 'Approver'
  if (key === 'requester') return 'Requester'
  return role || ''
}

function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="group flex items-center gap-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-base-content/30">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-neutral text-sm font-semibold tracking-tight text-neutral-content"
        aria-hidden
      >
        BF
      </span>
      {!compact ? (
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold tracking-tight text-base-content">
            BPMFlow AI
          </span>
          <span className="block truncate text-xs text-base-content/60">
            Business Process Management
          </span>
        </span>
      ) : null}
    </Link>
  )
}

function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const { user, session, signOut } = useAuth()

  return (
    <div className="flex h-full flex-col bg-base-100">
      <div className="border-b border-base-200 px-4 py-5">
        <BrandMark />
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4" aria-label="Primary">
        <div className="space-y-0.5">
          {PRIMARY_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={navClassName}
              onClick={onNavigate}
            >
              {item.label}
            </NavLink>
          ))}
        </div>

        <div>
          <div className="mx-3 mb-2 border-t border-base-200" />
          <div className="space-y-0.5">
            {SECONDARY_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={navClassName}
                onClick={onNavigate}
              >
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>

      <div className="border-t border-base-200 p-4">
        {session && user ? (
          <div className="space-y-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-base-content">
                {user.full_name || user.email}
              </p>
              <p className="truncate text-xs text-base-content/60">{formatRoleLabel(user.role)}</p>
            </div>
            <button
              type="button"
              onClick={() => void signOut()}
              className="btn btn-ghost btn-sm h-9 w-full justify-start px-2 font-medium"
            >
              Sign out
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Link to="/sign-in" className="btn btn-primary btn-sm" onClick={onNavigate}>
              Sign in
            </Link>
            <Link to="/sign-up" className="btn btn-ghost btn-sm" onClick={onNavigate}>
              Sign up
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}

function TopHeader({
  title,
  drawerId,
}: {
  title: string
  drawerId: string
}) {
  const { user, session, signOut } = useAuth()
  const displayName = user?.full_name || user?.email || 'Account'

  return (
    <header className="sticky top-0 z-20 border-b border-base-200 bg-base-100/90 backdrop-blur">
      <div className="flex h-14 items-center justify-between gap-4 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <label
            htmlFor={drawerId}
            className="btn btn-ghost btn-square btn-sm lg:hidden"
            aria-label="Open navigation"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.75} d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </label>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium uppercase tracking-[0.14em] text-base-content/45">
              BPMFlow AI
            </p>
            <h1 className="truncate text-base font-semibold tracking-tight text-base-content">{title}</h1>
          </div>
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <button
            type="button"
            className="btn btn-ghost btn-square btn-sm"
            aria-label="Notifications"
            title="Notifications"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.75}
                d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0a3 3 0 11-6 0"
              />
            </svg>
          </button>

          <div className="dropdown dropdown-end">
            <div
              tabIndex={0}
              role="button"
              className="btn btn-ghost h-9 gap-2 px-2"
              aria-label="Account menu"
            >
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-base-200 text-xs font-semibold text-base-content">
                {(displayName.trim()[0] || 'U').toUpperCase()}
              </span>
              <span className="hidden max-w-[10rem] truncate text-sm font-medium sm:inline">
                {session && user ? displayName : 'Guest'}
              </span>
            </div>
            <ul
              tabIndex={0}
              className="menu dropdown-content z-30 mt-2 w-56 rounded-xl border border-base-200 bg-base-100 p-2 shadow-lg"
            >
              {session && user ? (
                <>
                  <li className="menu-title px-2 py-1">
                    <span className="normal-case tracking-normal text-base-content/60">
                      {user.email}
                      <span className="mt-0.5 block text-base-content/45">
                        {formatRoleLabel(user.role)}
                      </span>
                    </span>
                  </li>
                  <li>
                    <Link to="/settings">Settings</Link>
                  </li>
                  <li>
                    <button type="button" onClick={() => void signOut()}>
                      Sign out
                    </button>
                  </li>
                </>
              ) : (
                <>
                  <li>
                    <Link to="/sign-in">Sign in</Link>
                  </li>
                  <li>
                    <Link to="/sign-up">Sign up</Link>
                  </li>
                </>
              )}
            </ul>
          </div>
        </div>
      </div>
    </header>
  )
}

export default function AppShell() {
  const location = useLocation()
  const drawerId = useId().replace(/:/g, '')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const title = useMemo(() => pageTitleFor(location.pathname), [location.pathname])
  const isAuthRoute = location.pathname === '/sign-in' || location.pathname === '/sign-up'
  const { error } = useAuth()

  useEffect(() => {
    setDrawerOpen(false)
  }, [location.pathname])

  if (isAuthRoute) {
    return (
      <div className="min-h-screen bg-base-200 text-base-content">
        <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-10 sm:px-6">
          <div className="mb-8 flex flex-col items-center text-center">
            <BrandMark />
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-base-content/65">
              Human-supervised business process management with AI assistance and clear oversight.
            </p>
          </div>
          {error ? (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
              {error}
            </div>
          ) : null}
          <Outlet />
          <p className="mt-8 text-center text-xs text-base-content/45">
            BPMFlow AI · Secure workspace access
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="drawer lg:drawer-open">
      <input
        id={drawerId}
        type="checkbox"
        className="drawer-toggle"
        checked={drawerOpen}
        onChange={(e) => setDrawerOpen(e.target.checked)}
      />

      <div className="drawer-content flex min-h-screen flex-col bg-base-200 text-base-content">
        <TopHeader title={title} drawerId={drawerId} />

        {error ? (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-950 sm:px-6">
            {error}
          </div>
        ) : null}

        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>

      <div className="drawer-side z-40">
        <label htmlFor={drawerId} aria-label="Close navigation" className="drawer-overlay" />
        <aside className="flex min-h-full w-72 flex-col border-r border-base-200 bg-base-100 text-base-content">
          <SidebarNav onNavigate={() => setDrawerOpen(false)} />
        </aside>
      </div>
    </div>
  )
}
