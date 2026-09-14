import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import SystemHealthPage from './SystemHealthPage'

vi.mock('../../services/apiClient', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'ok', env: 'development', database: 'ok' }),
  getDemoHealth: vi.fn().mockResolvedValue({
    env: 'development',
    debug: true,
    mock_llm: true,
    gemini_offline: true,
    email_dry_run: true,
    persistence_mode: 'supabase',
    supabase_url_configured: true,
    jwt_secret_configured: true,
    database_url_configured: true,
    gemini_configured: false,
    allowed_file_types: ['pdf'],
    max_upload_mb: 10,
    tool_registry_allowlist_size: 4,
    migrations_on_disk: ['0024.sql'],
    python_runner_migrations: ['0001'],
    migration_0024_on_disk: true,
    note: 'This payload never returns API keys, JWT secrets, or passwords.',
  }),
}))

describe('SystemHealthPage', () => {
  it('renders health and demo readiness without secrets', async () => {
    render(
      <MemoryRouter>
        <SystemHealthPage />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/Demo readiness looks usable/)).toBeInTheDocument()
    expect(screen.getByText('Backend health')).toBeInTheDocument()
    expect(screen.getAllByText('ok').length).toBeGreaterThan(0)
    expect(screen.getAllByText('development').length).toBeGreaterThan(0)
    expect(screen.getByText(/never returns API keys/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/sk-|service.role|eyJ/)
  })
})
