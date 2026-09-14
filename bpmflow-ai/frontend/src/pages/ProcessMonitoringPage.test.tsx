import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProcessMonitoringPage from './ProcessMonitoringPage'

const { getProcessMonitoring, calculateProcessKpis } = vi.hoisted(() => ({
  getProcessMonitoring: vi.fn(),
  calculateProcessKpis: vi.fn(),
}))

vi.mock('../services/apiClient', () => ({
  getProcessMonitoring,
  calculateProcessKpis,
}))

const PROCESS_ID = '11111111-1111-1111-1111-111111111111'

describe('ProcessMonitoringPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders timeline, KPIs, bottlenecks, and exception analytics from the backend', async () => {
    getProcessMonitoring.mockResolvedValue({
      process_id: PROCESS_ID,
      tenant_id: 't1',
      state: 'COMPLETED',
      status: 'COMPLETED',
      duration_seconds: null,
      timeline: [
        { process_id: PROCESS_ID, event_type: 'PROCESS_CREATED', timestamp: '2026-01-01T00:00:00Z' },
        { process_id: PROCESS_ID, event_type: 'INVOICE_MATCHING', timestamp: '2026-01-02T00:00:00Z' },
      ],
      kpis: {
        tenant_id: 't1',
        total_exceptions: 2,
        average_completion_time_seconds: '120',
        average_human_wait_time_seconds: null,
        insufficient_evidence: true,
        completion_rate: '0',
      },
      bottlenecks: [{ step: 'Finance Approval', average_duration_seconds: '90', reason: ['Waited on approver'] }],
      exception_analytics: {
        total_exceptions: 2,
        open_exceptions: 1,
        resolved_exceptions: 1,
        exceptions_by_code: { INVOICE_MISMATCH: 2 },
        most_frequent_exception: 'INVOICE_MISMATCH',
      },
    })
    render(
      <MemoryRouter initialEntries={[`/processes/${PROCESS_ID}/monitoring`]}>
        <Routes>
          <Route path="/processes/:processId/monitoring" element={<ProcessMonitoringPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Process Created')).toBeInTheDocument()
    expect(screen.getByText('Invoice Matching')).toBeInTheDocument()
    expect(screen.getAllByText('Duration unavailable').length).toBeGreaterThan(0)
    expect(screen.getByText('Insufficient evidence. KPI values below are what the backend returned, including zeros.')).toBeInTheDocument()
    expect(screen.getByText('Finance Approval')).toBeInTheDocument()
    expect(screen.getByText('Observed bottleneck')).toBeInTheDocument()
    expect(screen.getByText('INVOICE_MISMATCH')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/2026-99-99/)
  })
})
