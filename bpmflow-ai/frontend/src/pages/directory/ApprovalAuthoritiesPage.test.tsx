import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ApprovalAuthoritiesPage from './ApprovalAuthoritiesPage'

const listDirectoryApprovers = vi.fn()

vi.mock('../../services/apiClient', () => ({
  listDirectoryApprovers: (...args: unknown[]) => listDirectoryApprovers(...args),
}))

describe('ApprovalAuthoritiesPage', () => {
  it('looks up authorities through the existing approvers API', async () => {
    listDirectoryApprovers.mockResolvedValue([
      {
        employee_id: 'e1',
        employee_number: 'EMP-01',
        full_name: 'Ada Finance',
        email: 'ada@company.test',
        role_name: 'Finance Manager',
        role_code: 'FM',
        authority_code: 'L2',
        approval_type: 'PURCHASE',
        max_amount: '5000',
        currency: 'USD',
      },
    ])
    render(
      <MemoryRouter>
        <ApprovalAuthoritiesPage />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Approval authority is used by Agent3/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Approval type'), 'PURCHASE')
    await userEvent.click(screen.getByRole('button', { name: 'Look up authorities' }))
    await waitFor(() => expect(listDirectoryApprovers).toHaveBeenCalledWith({ approval_type: 'PURCHASE', amount: undefined, currency: undefined }))
    expect(await screen.findByText('Ada Finance')).toBeInTheDocument()
    expect(screen.getByText('5000 USD')).toBeInTheDocument()
  })
})
