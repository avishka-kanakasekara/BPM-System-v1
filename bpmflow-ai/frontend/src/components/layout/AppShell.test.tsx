import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import AppShell from './AppShell'

const authState = vi.hoisted(() => ({
  user: { id: 'u1', email: 'a@example.com', role: 'requester' as string, tenant_id: 't1', full_name: 'Ada' },
}))

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
    session: { access_token: 't' },
    loading: false,
    error: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    refreshProfile: vi.fn(),
  }),
}))

describe('AppShell administration navigation', () => {
  it('shows directory and tools to a requester but hides system health', () => {
    authState.user.role = 'requester'
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>,
    )
    expect(screen.getByText('Governance')).toBeInTheDocument()
    expect(screen.getByText('Operations')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Exceptions' })).toHaveAttribute('href', '/exceptions')
    expect(screen.getByRole('link', { name: 'Company Directory' })).toHaveAttribute('href', '/directory')
    expect(screen.getByRole('link', { name: 'Tool Registry' })).toHaveAttribute('href', '/tools')
    expect(screen.queryByRole('link', { name: 'System Health' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Approvals' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Company Policies' })).not.toBeInTheDocument()
  })

  it('shows system health for admin', () => {
    authState.user.role = 'admin'
    render(
      <MemoryRouter>
        <AppShell />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'System Health' })).toHaveAttribute('href', '/admin/system')
    expect(screen.getByRole('link', { name: 'Approvals' })).toHaveAttribute('href', '/approvals')
    expect(screen.getByRole('link', { name: 'Company Policies' })).toHaveAttribute('href', '/policies')
  })
})
