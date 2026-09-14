import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProcessDetailPage from './ProcessDetailPage'
import type { ApprovalRecord, ProcessRecord, WorkflowPlanRecord, WorkflowStepRecord } from '../types/api'

const {
  getProcess,
  getDiscoveredProcess,
  getProcessWorkflow,
  getProcessPurchaseOrder,
  getProcessMonitoring,
  getVendor,
  listApprovals,
  listAuditLogs,
  listExecutionReceipts,
  listProcessExceptions,
  listProcessInvoices,
  listProcessQuotations,
  listTobeRecommendations,
  listWorkflowSteps,
  startProcess,
  planResources,
  riskReview,
  completeInvoiceMatching,
  executeWorkflowStep,
  activateWorkflowPlan,
  planProcessWorkflow,
  validateWorkflowPlan,
  decideApproval,
} = vi.hoisted(() => ({
  getProcess: vi.fn(),
  getDiscoveredProcess: vi.fn(),
  getProcessWorkflow: vi.fn(),
  getProcessPurchaseOrder: vi.fn(),
  getProcessMonitoring: vi.fn(),
  getVendor: vi.fn(),
  listApprovals: vi.fn(),
  listAuditLogs: vi.fn(),
  listExecutionReceipts: vi.fn(),
  listProcessExceptions: vi.fn(),
  listProcessInvoices: vi.fn(),
  listProcessQuotations: vi.fn(),
  listTobeRecommendations: vi.fn(),
  listWorkflowSteps: vi.fn(),
  startProcess: vi.fn(),
  planResources: vi.fn(),
  riskReview: vi.fn(),
  completeInvoiceMatching: vi.fn(),
  executeWorkflowStep: vi.fn(),
  activateWorkflowPlan: vi.fn(),
  planProcessWorkflow: vi.fn(),
  validateWorkflowPlan: vi.fn(),
  decideApproval: vi.fn(),
}))

const authState = vi.hoisted(() => ({
  user: {
    id: 'user-1',
    email: 'a@example.com',
    role: 'requester' as string,
    tenant_id: '00000000-0000-0000-0000-000000000001',
  },
}))

vi.mock('../auth/AuthContext', () => ({
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

vi.mock('../services/apiClient', () => ({
  apiErrorMessage: (err: unknown) => (err as Error).message || 'Request failed',
  getProcess,
  getDiscoveredProcess,
  getProcessWorkflow,
  getProcessPurchaseOrder,
  getProcessMonitoring,
  getVendor,
  listApprovals,
  listAuditLogs,
  listExecutionReceipts,
  listProcessExceptions,
  listProcessInvoices,
  listProcessQuotations,
  listTobeRecommendations,
  listWorkflowSteps,
  startProcess,
  planResources,
  riskReview,
  completeInvoiceMatching,
  executeWorkflowStep,
  activateWorkflowPlan,
  planProcessWorkflow,
  validateWorkflowPlan,
  decideApproval,
  resolveException: vi.fn(),
  retryException: vi.fn(),
  failException: vi.fn(),
}))

const PROCESS_ID = '11111111-1111-1111-1111-111111111111'

function notFound() {
  return Promise.reject({ response: { status: 404 } })
}

function baseProcess(stage: ProcessRecord['current_stage'], extra: Partial<ProcessRecord> = {}): ProcessRecord {
  return {
    id: PROCESS_ID,
    name: 'Office laptops',
    description: 'Buy laptops',
    process_type: 'PROCUREMENT',
    status: 'ACTIVE',
    current_stage: stage,
    version: 1,
    created_by: 'requester-1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    tenant_id: authState.user.tenant_id,
    ...extra,
  }
}

const poStep: WorkflowStepRecord = {
  id: 'step-po',
  tenant_id: authState.user.tenant_id!,
  workflow_plan_id: 'plan-1',
  step_key: 'create_po',
  sequence: 5,
  name: 'Create Purchase Order',
  step_type: 'SYSTEM_ACTION',
  status: 'READY',
  required_action: 'CREATE_PO',
  required_tool_category: 'PROCUREMENT',
}

function plan(status: WorkflowPlanRecord['status'], steps: WorkflowStepRecord[] = [poStep]): WorkflowPlanRecord {
  return {
    id: 'plan-1',
    tenant_id: authState.user.tenant_id!,
    process_id: PROCESS_ID,
    version: 1,
    status,
    steps,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  }
}

const pendingApproval: ApprovalRecord = {
  id: 'appr-1',
  process_id: PROCESS_ID,
  status: 'PENDING',
  risk_level: 'HIGH',
  reason: 'Amount exceeds policy threshold',
  requested_by: 'requester-1',
  approver_id: 'approver-1',
  created_at: '2026-01-03T00:00:00Z',
}

function stubSecondary() {
  getDiscoveredProcess.mockRejectedValue({ response: { status: 404 } })
  getProcessWorkflow.mockRejectedValue({ response: { status: 404 } })
  getProcessPurchaseOrder.mockRejectedValue({ response: { status: 404 } })
  getProcessMonitoring.mockRejectedValue({ response: { status: 404 } })
  listApprovals.mockResolvedValue([])
  listAuditLogs.mockResolvedValue([])
  listExecutionReceipts.mockResolvedValue([])
  listProcessExceptions.mockResolvedValue([])
  listProcessInvoices.mockResolvedValue([])
  listProcessQuotations.mockResolvedValue([])
  listTobeRecommendations.mockResolvedValue([])
  getVendor.mockRejectedValue({ response: { status: 404 } })
  listWorkflowSteps.mockResolvedValue([])
}

async function renderCockpit(stage: ProcessRecord['current_stage'], processExtra: Partial<ProcessRecord> = {}) {
  getProcess.mockResolvedValue(baseProcess(stage, processExtra))
  render(
    <MemoryRouter initialEntries={[`/processes/${PROCESS_ID}`]}>
      <Routes>
        <Route path="/processes/:processId" element={<ProcessDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
  await screen.findByText('Office laptops')
}

describe('Process Cockpit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState.user.role = 'requester'
    stubSecondary()
  })

  it('shows a loading state then the process', async () => {
    let resolveProcess: (value: ProcessRecord) => void = () => undefined
    getProcess.mockReturnValue(new Promise<ProcessRecord>((resolve) => {
      resolveProcess = resolve
    }))
    render(
      <MemoryRouter initialEntries={[`/processes/${PROCESS_ID}`]}>
        <Routes>
          <Route path="/processes/:processId" element={<ProcessDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
    resolveProcess(baseProcess('DRAFT'))
    expect(await screen.findByText('Office laptops')).toBeInTheDocument()
  })

  it('shows an error state with retry when the process fails to load', async () => {
    getProcess.mockRejectedValue({ response: { status: 503 }, message: 'down' })
    render(
      <MemoryRouter initialEntries={[`/processes/${PROCESS_ID}`]}>
        <Routes>
          <Route path="/processes/:processId" element={<ProcessDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Unable to load process')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('DRAFT shows Start discovery and not Autopilot', async () => {
    await renderCockpit('DRAFT')
    expect(screen.getByRole('button', { name: 'Start discovery' })).toBeInTheDocument()
    expect(screen.queryByText(/autopilot/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/run process automatically/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /execute all/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /execute workflow/i })).not.toBeInTheDocument()
    expect(screen.getByText('Discovers process facts and evidence.')).toBeInTheDocument()
    expect(screen.getByText(/one authorized Workflow Step using a registered allow-listed tool/)).toBeInTheDocument()
    expect(screen.getByText(/does not automatically change the workflow/)).toBeInTheDocument()
  })

  it('DISCOVERING shows discovery UI', async () => {
    await renderCockpit('DISCOVERING')
    expect(screen.getByText('Understand this process')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /plan resources from directory/i })).toBeInTheDocument()
  })

  it('RESOURCE_PLANNING does not use hardcoded Agent 3 requirements', async () => {
    await renderCockpit('RESOURCE_PLANNING')
    expect(screen.getByText('Resource Allocation')).toBeInTheDocument()
    expect(screen.getByText(/Agent 3 — Workforce/)).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/SYN-DEP-FIN/)
    expect(document.body.textContent).not.toMatch(/\bpython\b/i)
    expect(document.body.textContent).not.toMatch(/\bfastapi\b/i)
    const planBtn = screen.getByRole('button', { name: /plan resources from directory/i })
    await userEvent.click(planBtn)
    await waitFor(() => expect(planResources).toHaveBeenCalled())
    const payload = planResources.mock.calls[0][1]
    expect(payload.human_requirements).toBeUndefined()
    expect(JSON.stringify(payload)).not.toMatch(/developer|python|fastapi|SYN-DEP/)
  })

  it('RISK_REVIEW displays backend risk data', async () => {
    await renderCockpit('RISK_REVIEW', {
      metadata_json: {
        last_risk_assessment: {
          findings: [
            {
              risk_level: 'HIGH',
              risk_type: 'POLICY_VIOLATION',
              description: 'Missing three quotations',
              recommendation: 'Attach quotation evidence',
              policy_version: 'POL-1',
            },
          ],
        },
      },
    })
    expect(screen.getByText('Risk review')).toBeInTheDocument()
    expect(screen.getByText('POLICY_VIOLATION')).toBeInTheDocument()
    expect(screen.getByText('Missing three quotations')).toBeInTheDocument()
    expect(screen.getByText(/POL-1/)).toBeInTheDocument()
  })

  it('renders actual WorkflowPlan steps', async () => {
    getProcessWorkflow.mockResolvedValue(
      plan('DRAFT', [
        { ...poStep, sequence: 1, id: 's1', name: 'Review Purchase Request', step_type: 'HUMAN_TASK', status: 'COMPLETED' },
        { ...poStep, sequence: 2, id: 's2', name: 'Finance Approval', step_type: 'APPROVAL', status: 'AUTHORIZED' },
      ]),
    )
    await renderCockpit('RISK_REVIEW')
    expect(screen.getByText('1. Review Purchase Request')).toBeInTheDocument()
    expect(screen.getByText('2. Finance Approval')).toBeInTheDocument()
    expect(screen.queryByText('Create Purchase Order')).not.toBeInTheDocument()
  })

  it('does not show approval controls to a requester', async () => {
    authState.user.role = 'requester'
    await renderCockpit('AWAITING_HUMAN_APPROVAL')
    expect(screen.getByText('Waiting for an authorized approver.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reject' })).not.toBeInTheDocument()
    expect(listApprovals).not.toHaveBeenCalled()
  })

  it('shows approval controls to an approver', async () => {
    authState.user.role = 'approver'
    listApprovals.mockResolvedValue([pendingApproval])
    await renderCockpit('AWAITING_HUMAN_APPROVAL')
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /request changes/i })).not.toBeInTheDocument()
  })

  it('shows explicit Activate workflow for an authorized role', async () => {
    authState.user.role = 'approver'
    getProcessWorkflow.mockResolvedValue(plan('READY'))
    await renderCockpit('WORKFLOW_EXECUTION')
    const activate = screen.getByRole('button', { name: 'Activate workflow' })
    expect(activate).toBeInTheDocument()
    expect(screen.getByText(/Activation authorizes the workflow plan for execution/)).toBeInTheDocument()
    await userEvent.click(activate)
    await waitFor(() => expect(activateWorkflowPlan).toHaveBeenCalledWith('plan-1'))
  })

  it('WORKFLOW_EXECUTION calls one-step execution, not legacy Agent 2 execute', async () => {
    authState.user.role = 'approver'
    getProcessWorkflow.mockResolvedValue(plan('ACTIVE'))
    executeWorkflowStep.mockResolvedValue({
      execution_status: 'COMPLETED',
      workflow_plan_id: 'plan-1',
      workflow_step_id: 'step-po',
      process_id: PROCESS_ID,
      receipt_id: 'rcpt-1',
      step_status: 'COMPLETED',
      tool_name: 'create_purchase_order',
    })
    await renderCockpit('WORKFLOW_EXECUTION')
    expect(screen.queryByLabelText(/tool name/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    const execute = screen.getByRole('button', { name: 'Execute step' })
    await userEvent.click(execute)
    await waitFor(() =>
      expect(executeWorkflowStep).toHaveBeenCalledWith('plan-1', 'step-po', { process_id: PROCESS_ID }),
    )
    expect(executeWorkflowStep.mock.calls[0][2]).not.toHaveProperty('tool_name')
  })

  it('invoice matching does not send expected_* truth', async () => {
    completeInvoiceMatching.mockResolvedValue({
      process_id: PROCESS_ID,
      current_stage: 'COMPLETED',
      success: true,
      message: 'Matched',
    })
    listProcessInvoices.mockResolvedValue([
      {
        invoice_id: 'inv-1',
        tenant_id: authState.user.tenant_id,
        invoice_number: 'INV-9',
        vendor_id: 'v1',
        purchase_order_id: 'po1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '100',
        tax: '10',
        total: '110',
        status: 'RECEIVED',
      },
    ])
    await renderCockpit('INVOICE_MATCHING')
    expect(screen.getAllByText(/INV-9/).length).toBeGreaterThan(0)
    expect(screen.queryByLabelText(/expected/i)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Match persisted invoice' }))
    await waitFor(() => expect(completeInvoiceMatching).toHaveBeenCalledWith(PROCESS_ID, {}))
    const sent = completeInvoiceMatching.mock.calls[0][1]
    expect(sent).toEqual({})
    expect(JSON.stringify(sent)).not.toMatch(/expected_/)
  })

  it('EXCEPTION renders exception UI', async () => {
    authState.user.role = 'admin'
    listProcessExceptions.mockResolvedValue([
      {
        id: 'ex-1',
        process_id: PROCESS_ID,
        exception_code: 'INVOICE_MISMATCH',
        title: 'Invoice does not match PO',
        severity: 'high',
        type: 'INVOICE_MISMATCH',
        description: 'Totals differ',
        status: 'open',
        created_at: '2026-01-04T00:00:00Z',
      },
    ])
    await renderCockpit('EXCEPTION')
    expect(screen.getByText('Invoice does not match PO')).toBeInTheDocument()
    expect(screen.getByText(/INVOICE_MISMATCH/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Resolve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fail' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View exception' })).toHaveAttribute('href', '/exceptions/ex-1')
  })

  it('COMPLETED has no execution action', async () => {
    getProcessWorkflow.mockResolvedValue(plan('ACTIVE'))
    await renderCockpit('COMPLETED')
    expect(screen.getAllByText(/Execution actions are closed/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Execute step' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start discovery' })).not.toBeInTheDocument()
  })

  it('procurement summary uses backend records and links, not hardcoded demo facts', async () => {
    listProcessQuotations.mockResolvedValue([
      {
        quotation_id: 'q-1',
        tenant_id: authState.user.tenant_id,
        quotation_number: 'Q-77',
        vendor_id: 'vendor-22',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '50',
        tax: '5',
        total: '55',
        status: 'RECEIVED',
      },
      {
        quotation_id: 'q-2',
        tenant_id: authState.user.tenant_id,
        quotation_number: 'Q-78',
        vendor_id: 'vendor-22',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '60',
        tax: '6',
        total: '66',
        status: 'RECEIVED',
      },
    ])
    getProcessPurchaseOrder.mockResolvedValue({
      purchase_order_id: 'po-1',
      tenant_id: authState.user.tenant_id,
      po_number: 'PO-TEST-1',
      process_id: PROCESS_ID,
      vendor_id: 'vendor-22',
      currency: 'USD',
      subtotal: '50',
      tax: '5',
      total: '55',
      status: 'ISSUED',
    })
    listProcessInvoices.mockResolvedValue([
      {
        invoice_id: 'inv-sum',
        tenant_id: authState.user.tenant_id,
        invoice_number: 'INV-TEST-1',
        vendor_id: 'vendor-22',
        purchase_order_id: 'po-1',
        process_id: PROCESS_ID,
        currency: 'USD',
        subtotal: '50',
        tax: '5',
        total: '55',
        status: 'MATCHED',
        match_result: { matched: true, status: 'MATCHED' },
      },
    ])
    getVendor.mockResolvedValue({
      vendor_id: 'vendor-22',
      tenant_id: authState.user.tenant_id,
      vendor_code: 'V-22',
      legal_name: 'Acme Components',
      status: 'active',
    })
    await renderCockpit('INVOICE_MATCHING')
    expect(await screen.findByText('Acme Components')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '2' })).toHaveAttribute('href', `/quotations?process=${PROCESS_ID}`)
    expect(screen.getByRole('link', { name: 'PO-TEST-1' })).toHaveAttribute(
      'href',
      `/purchase-orders/${PROCESS_ID}`,
    )
    expect(screen.getAllByRole('link', { name: 'INV-TEST-1' })[0]).toHaveAttribute('href', '/invoices/inv-sum')
    expect(screen.getAllByText('MATCHED').length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toMatch(/BPM Supplies Ltd/)
    expect(document.body.textContent).not.toMatch(/PR-2026-0098/)
    expect(document.body.textContent).not.toMatch(/PO-2026-0451/)
  })

  it('shows a monitoring summary and TO-BE link from backend data', async () => {
    getProcessMonitoring.mockResolvedValue({
      process_id: PROCESS_ID,
      tenant_id: authState.user.tenant_id,
      state: 'COMPLETED',
      status: 'COMPLETED',
      kpis: {
        tenant_id: authState.user.tenant_id,
        insufficient_evidence: false,
        total_exceptions: 1,
        average_human_wait_time_seconds: null,
      },
      bottlenecks: [{ step: 'Finance Approval', reason: ['Long wait'] }],
      exception_analytics: { total_exceptions: 1, open_exceptions: 0, resolved_exceptions: 1 },
      timeline: [],
    })
    listTobeRecommendations.mockResolvedValue([
      {
        id: 'rec-1',
        tenant_id: authState.user.tenant_id,
        process_id: PROCESS_ID,
        recommendation_type: 'BOTTLENECK',
        title: 'Shorten finance wait',
        description: 'Parallelize review',
        reason: 'Long wait',
        status: 'PROPOSED',
        fingerprint: 'fp',
        created_at: '2026-01-05T00:00:00Z',
        activates_workflow: false,
      },
    ])
    await renderCockpit('COMPLETED')
    expect(screen.getAllByRole('link', { name: 'Open monitoring' })[0]).toHaveAttribute(
      'href',
      `/processes/${PROCESS_ID}/monitoring`,
    )
    expect(screen.getAllByRole('link', { name: 'TO-BE recommendations' })[0]).toHaveAttribute(
      'href',
      `/recommendations?process=${PROCESS_ID}`,
    )
    expect(screen.getByRole('link', { name: 'Shorten finance wait' })).toHaveAttribute('href', '/recommendations/rec-1')
    expect(screen.getByText('Duration unavailable')).toBeInTheDocument()
  })
})
