import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import VendorsPage from './VendorsPage'

const { listVendors, createVendor } = vi.hoisted(() => ({
  listVendors: vi.fn(),
  createVendor: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  user: {
    id: 'user-1',
    email: 'a@example.com',
    role: 'requester' as string,
    tenant_id: '00000000-0000-0000-0000-000000000001',
  },
}))

vi.mock('../../auth/AuthContext', () => ({
  useAuth: () => ({
    user: authState.user,
    session: { access_token: 'test' },
    loading: false,
    error: null,
    signIn: vi.fn(),
    signUp: vi.fn(),
    signOut: vi.fn(),
    refreshProfile: vi.fn(),
  }),
}))

vi.mock('../../services/apiClient', () => ({
  listVendors,
  createVendor,
}))

describe('VendorsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'requester'
  })

  it('renders tenant vendors from the API', async () => {
    listVendors.mockResolvedValue([
      {
        vendor_id: 'v-1',
        tenant_id: authState.user.tenant_id,
        vendor_code: 'VEN-01',
        legal_name: 'Northwind Parts',
        status: 'active',
        phone: '555-0100',
        website: 'https://example.test',
        notes: 'Preferred',
      },
    ])
    render(
      <MemoryRouter>
        <VendorsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('VEN-01')).toBeInTheDocument()
    expect(screen.getByText('Northwind Parts')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByText('555-0100')).toBeInTheDocument()
  })

  it('shows an empty state when no vendors are returned', async () => {
    listVendors.mockResolvedValue([])
    render(
      <MemoryRouter>
        <VendorsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText('No vendors')).toBeInTheDocument()
  })

  it('hides vendor creation for a requester', async () => {
    listVendors.mockResolvedValue([])
    render(
      <MemoryRouter>
        <VendorsPage />
      </MemoryRouter>,
    )
    await screen.findByText('No vendors')
    expect(screen.queryByRole('button', { name: 'Create vendor' })).not.toBeInTheDocument()
    expect(screen.queryByText('Add vendor')).not.toBeInTheDocument()
  })

  it('shows admin vendor creation', async () => {
    authState.user.role = 'admin'
    listVendors.mockResolvedValue([])
    render(
      <MemoryRouter>
        <VendorsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('button', { name: 'Create vendor' })).toBeInTheDocument()
    await waitFor(() => expect(listVendors).toHaveBeenCalled())
  })
})
