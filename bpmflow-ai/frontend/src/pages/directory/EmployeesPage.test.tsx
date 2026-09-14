import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EmployeesPage from './EmployeesPage'

const { listEmployees, listDepartments, listCompanyRoles, createEmployee } = vi.hoisted(() => ({
  listEmployees: vi.fn(),
  listDepartments: vi.fn(),
  listCompanyRoles: vi.fn(),
  createEmployee: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  user: { id: 'u1', email: 'a@example.com', role: 'requester' as string, tenant_id: 't1' },
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

vi.mock('../../services/apiClient', () => ({
  listEmployees,
  listDepartments,
  listCompanyRoles,
  createEmployee,
}))

describe('EmployeesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'requester'
    listDepartments.mockResolvedValue([{ department_id: 'd1', tenant_id: 't1', name: 'Finance', code: 'FIN' }])
    listCompanyRoles.mockResolvedValue([{ role_id: 'r1', tenant_id: 't1', name: 'Analyst', code: 'ANL' }])
  })

  it('renders employees from the directory API', async () => {
    listEmployees.mockResolvedValue([
      {
        employee_id: 'e1',
        tenant_id: 't1',
        employee_number: 'EMP-01',
        full_name: 'Ada Finance',
        email: 'ada@company.test',
        department_id: 'd1',
        role_id: 'r1',
        status: 'active',
        skill_codes: ['PROCUREMENT'],
        is_available: true,
        current_workload_pct: '20',
      },
    ])
    render(
      <MemoryRouter>
        <EmployeesPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Ada Finance')).toBeInTheDocument()
    expect(screen.getByText('EMP-01')).toBeInTheDocument()
    expect(screen.getByText('ada@company.test')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ada Finance' })).toHaveAttribute('href', '/directory/employees/e1')
    expect(screen.queryByRole('button', { name: 'Create employee' })).not.toBeInTheDocument()
  })

  it('shows empty state', async () => {
    listEmployees.mockResolvedValue([])
    render(
      <MemoryRouter>
        <EmployeesPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No employees')).toBeInTheDocument()
  })

  it('shows admin create when role is admin', async () => {
    authState.user.role = 'admin'
    listEmployees.mockResolvedValue([])
    render(
      <MemoryRouter>
        <EmployeesPage />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('button', { name: 'Create employee' })).toBeInTheDocument()
  })
})
