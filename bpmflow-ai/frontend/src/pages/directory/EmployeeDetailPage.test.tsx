import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import EmployeeDetailPage from './EmployeeDetailPage'

vi.mock('../../services/apiClient', () => ({
  getEmployee: vi.fn().mockResolvedValue({
    employee_id: 'e1',
    tenant_id: 't1',
    employee_number: 'EMP-01',
    full_name: 'Ada Finance',
    email: 'ada@company.test',
    department_id: 'd1',
    role_id: 'r1',
    status: 'active',
    resource_id: 'res-1',
    skill_codes: ['PROCUREMENT'],
    is_available: true,
    current_workload_pct: '20',
  }),
  listDepartments: vi.fn().mockResolvedValue([{ department_id: 'd1', tenant_id: 't1', name: 'Finance', code: 'FIN' }]),
  listCompanyRoles: vi.fn().mockResolvedValue([{ role_id: 'r1', tenant_id: 't1', name: 'Analyst', code: 'ANL' }]),
  listEmployees: vi.fn().mockResolvedValue([]),
}))

describe('EmployeeDetailPage', () => {
  it('renders directory identity and Agent 3 explanation', async () => {
    render(
      <MemoryRouter initialEntries={['/directory/employees/e1']}>
        <Routes>
          <Route path="/directory/employees/:employeeId" element={<EmployeeDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Ada Finance')).toBeInTheDocument()
    expect(screen.getByText('ada@company.test')).toBeInTheDocument()
    expect(
      screen.getByText(/Agent3 uses Company Directory data to resolve eligible employees\/resources/),
    ).toBeInTheDocument()
    expect(screen.getByText('res-1')).toBeInTheDocument()
  })
})
