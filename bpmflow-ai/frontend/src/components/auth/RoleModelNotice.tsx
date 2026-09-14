type AppRole = 'requester' | 'approver' | 'admin'

type RoleModelNoticeProps = {
  /** Emphasize that the selected role is applied at registration. */
  highlightRegistration?: boolean
}

const ROLES: Array<{ id: AppRole; label: string; summary: string }> = [
  {
    id: 'requester',
    label: 'Requester',
    summary: 'Create processes, upload evidence, and track work.',
  },
  {
    id: 'approver',
    label: 'Approver',
    summary: 'Review risk findings and approve or reject requests.',
  },
  {
    id: 'admin',
    label: 'Admin',
    summary: 'Manage company policies and tenant configuration.',
  },
]

export { ROLES }
export type { AppRole }

export default function RoleModelNotice({ highlightRegistration = false }: RoleModelNoticeProps) {
  return (
    <aside
      className="mb-4 rounded-lg border border-base-300 bg-base-200/50 px-4 py-3 text-sm text-base-content/80"
      aria-label="BPMFlow access roles"
    >
      <p className="font-medium text-base-content">Access roles</p>
      {highlightRegistration ? (
        <p className="mt-1.5 leading-relaxed">
          Choose the role you need below. Local registration applies that role to your account
          so you can test Requester, Approver, and Admin access.
        </p>
      ) : (
        <p className="mt-1.5 leading-relaxed">
          Choose the role for this account before signing in. Local development will sync that
          role onto your profile. Hidden menus are not a security control; the API enforces access.
        </p>
      )}
      <ul className="mt-3 space-y-2">
        {ROLES.map((role) => (
          <li key={role.id} className="flex gap-2">
            <span className="mt-0.5 min-w-[5.5rem] shrink-0 font-medium text-base-content">
              {role.label}
            </span>
            <span className="leading-snug text-base-content/70">{role.summary}</span>
          </li>
        ))}
      </ul>
    </aside>
  )
}
