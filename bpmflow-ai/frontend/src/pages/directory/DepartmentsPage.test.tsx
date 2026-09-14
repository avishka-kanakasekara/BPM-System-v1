import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import DepartmentsPage from './DepartmentsPage'

vi.mock('../../services/apiClient', () => ({
  listDepartments: vi.fn().mockResolvedValue([
    { department_id: 'd1', tenant_id: 't1', name: 'Finance', code: 'FIN', status: 'active', manager_employee_id: 'e1' },
  ]),
  listEmployees: vi.fn().mockResolvedValue([
    {
      employee_id: 'e1',
      tenant_id: 't1',
      employee_number: 'EMP-01',
      full_name: 'Ada Finance',
      email: 'ada@company.test',
      department_id: 'd1',
      role_id: 'r1',
      status: 'active',
    },
  ]),
}))

describe('DepartmentsPage', () => {
  it('renders departments from the API', async () => {
    render(
      <MemoryRouter>
        <DepartmentsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Finance')).toBeInTheDocument()
    expect(screen.getByText('Code FIN')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })
})
