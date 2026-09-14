import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ToolsPage from './ToolsPage'

const { listRegistryTools, enableRegistryTool, disableRegistryTool } = vi.hoisted(() => ({
  listRegistryTools: vi.fn(),
  enableRegistryTool: vi.fn(),
  disableRegistryTool: vi.fn(),
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
  listRegistryTools,
  enableRegistryTool,
  disableRegistryTool,
}))

describe('ToolsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'requester'
    listRegistryTools.mockResolvedValue([
      {
        id: 'tool-1',
        tenant_id: 't1',
        tool_name: 'create_purchase_order',
        tool_category: 'PROCUREMENT',
        action_code: 'CREATE_PO',
        implementation_key: 'create_purchase_order',
        enabled: true,
        requires_authorization: true,
        allowed_step_types: ['SYSTEM_ACTION'],
      },
    ])
  })

  it('renders registered tools and security messaging without execution', async () => {
    render(
      <MemoryRouter>
        <ToolsPage />
      </MemoryRouter>,
    )
    expect(await screen.findAllByText('create_purchase_order')).toHaveLength(2)
    expect(screen.getByText(/Agent2 can execute only tools registered in the Tool Registry/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Disable' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /execute/i })).not.toBeInTheDocument()
  })

  it('shows enable/disable only for admin', async () => {
    authState.user.role = 'admin'
    render(
      <MemoryRouter>
        <ToolsPage />
      </MemoryRouter>,
    )
    expect(await screen.findByRole('button', { name: 'Disable' })).toBeInTheDocument()
  })
})
