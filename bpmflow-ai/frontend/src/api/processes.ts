import { apiClient, authHeaders } from './http'
import type {
  AdvanceProcessResponse,
  InvoiceMatchingPayload,
  InvoiceRecord,
  ProcessRecord,
  ProcessStartResponse,
  PurchaseOrderRecord,
  QuotationRecord,
  WorkflowPlanningResult,
  WorkflowPlanRecord,
  WorkflowResult,
  ExceptionRecord,
} from '../types/api'

export async function listProcesses(): Promise<ProcessRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessRecord[]>('/api/v1/processes', { headers })
  return response.data
}

export async function getProcess(processId: string): Promise<ProcessRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessRecord>(`/api/v1/processes/${processId}`, { headers })
  return response.data
}

export async function createProcess(payload: {
  name: string
  process_type: string
  description?: string
}): Promise<ProcessRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<ProcessRecord>('/api/v1/processes', payload, { headers })
  return response.data
}

/** DRAFT → DISCOVERING via Agent 4, then Agent 1 if available. */
export async function startProcess(processId: string): Promise<ProcessStartResponse> {
  const headers = await authHeaders()
  const response = await apiClient.post<ProcessStartResponse>(
    `/api/v1/processes/${processId}/start`,
    {},
    { headers },
  )
  return response.data
}

/**
 * Agent 4 convenience chain of agent-owned stages. Stops at human approval
 * and invoice evidence. Not a product “autopilot” and not unsupervised BPM.
 * Prefer explicit stage endpoints (start, plan-resources, risk-review, complete-invoice-matching).
 */
export async function advanceProcess(
  processId: string,
  payload: {
    correlation_id?: string
    idempotency_key?: string
    max_steps?: number
    reconcile_stale?: boolean
    invoice?: InvoiceMatchingPayload
    resource_planning?: {
      task_id: string
      tenant_id: string
      correlation_id?: string
      human_requirements?: Record<string, unknown>
      budget_requirements?: Record<string, unknown>
    }
  } = {},
): Promise<AdvanceProcessResponse> {
  const headers = await authHeaders()
  const response = await apiClient.post<AdvanceProcessResponse>(
    `/api/v1/processes/${processId}/advance`,
    payload,
    { headers },
  )
  return response.data
}

/** Agent 3 allocation through Agent 4. Omit invented skill lists; directory eligibility is server-side. */
export async function planResources(
  processId: string,
  payload: {
    task_id: string
    tenant_id: string
    correlation_id?: string
    process_context_ref?: string
    human_requirements?: Record<string, unknown>
    budget_requirements?: Record<string, unknown>
  },
): Promise<WorkflowResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowResult>(
    `/api/v1/processes/${processId}/plan-resources`,
    payload,
    { headers },
  )
  return response.data
}

export async function riskReview(
  processId: string,
  payload: Record<string, unknown> = {},
): Promise<WorkflowResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowResult>(
    `/api/v1/processes/${processId}/risk-review`,
    payload,
    { headers },
  )
  return response.data
}

/**
 * Agent 4 WORKFLOW_EXECUTION stage trigger. Not one-step Tool Registry execution.
 * Prefer POST /workflows/{planId}/steps/{stepId}/execute for Agent 2.
 */
export async function executeProcess(
  processId: string,
  payload: {
    task_id?: string
    task_type?: string
    correlation_id?: string
    parameters?: Record<string, unknown>
  } = {},
): Promise<WorkflowResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowResult>(
    `/api/v1/processes/${processId}/execute`,
    payload,
    { headers },
  )
  return response.data
}

/** Completion uses persisted invoices vs PO — do not send expected_* as truth. */
export async function completeInvoiceMatching(
  processId: string,
  payload: InvoiceMatchingPayload | string = {},
): Promise<WorkflowResult> {
  const headers = await authHeaders()
  const body =
    typeof payload === 'string' ? { notes: payload, reference: payload } : payload
  const response = await apiClient.post<WorkflowResult>(
    `/api/v1/processes/${processId}/complete-invoice-matching`,
    body,
    { headers },
  )
  return response.data
}

export async function planProcessWorkflow(processId: string): Promise<WorkflowPlanningResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowPlanningResult>(
    `/api/v1/processes/${processId}/workflow/plan`,
    {},
    { headers },
  )
  return response.data
}

export async function getProcessWorkflow(processId: string): Promise<WorkflowPlanRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<WorkflowPlanRecord>(
    `/api/v1/processes/${processId}/workflow`,
    { headers },
  )
  return response.data
}

export async function listProcessQuotations(processId: string): Promise<QuotationRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<QuotationRecord[]>(
    `/api/v1/processes/${processId}/quotations`,
    { headers },
  )
  return response.data
}

export async function getProcessPurchaseOrder(processId: string): Promise<PurchaseOrderRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<PurchaseOrderRecord>(
    `/api/v1/processes/${processId}/purchase-order`,
    { headers },
  )
  return response.data
}

export async function listProcessInvoices(processId: string): Promise<InvoiceRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<InvoiceRecord[]>(
    `/api/v1/processes/${processId}/invoices`,
    { headers },
  )
  return response.data
}

export async function listProcessExceptions(processId: string): Promise<ExceptionRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ExceptionRecord[]>(
    `/api/v1/processes/${processId}/exceptions`,
    { headers },
  )
  return response.data
}
