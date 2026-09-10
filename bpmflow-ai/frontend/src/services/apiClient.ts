import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { supabase } from './supabaseClient'

// In Vite dev, prefer same-origin + vite proxy (/api → :8000) unless overridden.
const configured = (import.meta.env.VITE_API_URL as string | undefined)?.trim()
const API_URL =
  configured && configured.length > 0
    ? configured
    : import.meta.env.DEV
      ? ''
      : 'http://localhost:8000'

const apiClient: AxiosInstance = axios.create({
  baseURL: API_URL,
})

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (config.data instanceof FormData) {
    config.headers.delete('Content-Type')
  } else if (!config.headers.get('Content-Type')) {
    config.headers.set('Content-Type', 'application/json')
  }
  return config
})

export async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) return {}
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function apiErrorMessage(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  return (err as Error).message || 'Request failed'
}

// --- Types -----------------------------------------------------------------

export type CurrentUser = {
  id: string
  email?: string | null
  full_name?: string | null
  role: string
  department?: string | null
  tenant_id?: string | null
}

export type HealthStatus = {
  status: string
  env?: string
  database?: string
  database_url_configured?: boolean
  supabase?: string
}

export type AgentMessage = {
  message_id: string
  process_id: string
  sender: string
  status: string
  overall_confidence: number
  payload: {
    process_name?: string | null
    activities?: Array<{
      name: string
      actor?: string | null
      system?: string | null
      avg_duration?: number | null
      entry_conditions?: string[]
      exit_conditions?: string[]
    }>
    rules?: Array<{ description: string; controls_activity?: string | null }>
    dependencies?: Array<{ predecessor: string; successor: string }>
    exceptions?: Array<{ kind: string; description: string; case_id?: string | null }>
    missing_or_contradictory_fields?: string[]
    discovery_errors?: string[]
  }
}

export type ProcessSummary = {
  process_id: string
  name: string
  status: string
  discovery_status?: string | null
  overall_confidence?: number | null
  activity_count: number
  created_at?: string | null
}

export type ProcessDetail = ProcessSummary & {
  process_json?: Record<string, unknown> | null
  description?: string | null
}

export type ProcessRecord = {
  id: string
  name: string
  description?: string | null
  process_type: string
  status: string
  current_stage: string
  version: number
  created_by?: string | null
  created_at: string
  updated_at: string
  metadata_json?: Record<string, unknown> | null
}

export type ProcessStartResponse = {
  process: ProcessRecord
  success: boolean
  message: string
  error_code?: string | null
  error_message?: string | null
  agent_response?: Record<string, unknown> | null
}

export type WorkflowResult = {
  process_id: string
  current_stage: string
  success: boolean
  message: string
  error_code?: string | null
  error_message?: string | null
  human_approval_required?: boolean
  eligible_for_execution?: boolean
  approval?: ApprovalRecord | null
  agent_response?: Record<string, unknown> | null
}

export type ApprovalRecord = {
  id: string
  process_id: string
  task_id?: string | null
  requested_by?: string | null
  approver_id?: string | null
  status: string
  risk_level: string
  reason: string
  decision?: string | null
  comments?: string | null
  created_at: string
  decided_at?: string | null
}

export type ApprovalDecisionResponse = {
  approval: ApprovalRecord
  decision: string
  workflow?: Record<string, unknown> | null
}

export type ExceptionRecord = {
  id: string
  process_id?: string | null
  task_id?: string | null
  severity: string
  type: string
  description: string
  status: string
  assigned_to?: string | null
  resolution_notes?: string | null
  created_at: string
  resolved_at?: string | null
}

export type AuditLogRecord = {
  id: string
  entity_type: string
  entity_id: string
  action: string
  performed_by?: string | null
  old_values?: Record<string, unknown> | null
  new_values?: Record<string, unknown> | null
  timestamp: string
}

export type ExecutionReceipt = {
  id: string
  process_id: string
  task_id: string
  tool_name: string
  action: string
  attempt_number: number
  idempotency_key: string
  status: string
  latency_ms?: number | null
  error_type?: string | null
  error_message?: string | null
  created_at: string
}

export type OptimizationRecommendation = {
  id: string
  process_id: string
  recommendation_type?: string
  problem?: string
  root_cause?: string
  evidence?: Record<string, unknown>
  baseline_metric?: number | string | null
  predicted_metric?: number | string | null
  improvement_percent?: number | null
  confidence?: number | null
  risk?: string | null
  status: string
  approved_by?: string
  approved_at?: string
  created_at?: string
}

export type Agent2AuditLog = {
  id: string
  actor?: string | null
  agent?: string | null
  action: string
  allowed?: boolean | null
  reason?: string | null
  timestamp?: string | null
}

// --- Health / Auth ---------------------------------------------------------

export async function getHealth(): Promise<HealthStatus> {
  const response = await apiClient.get<HealthStatus>('/health')
  return response.data
}

export async function getCurrentUser(): Promise<CurrentUser> {
  const headers = await authHeaders()
  const response = await apiClient.get<CurrentUser>('/api/v1/auth/me', { headers })
  return response.data
}

// --- Agent 1 ---------------------------------------------------------------

export async function discoverProcess(
  files: File[],
  processId?: string | null,
): Promise<AgentMessage> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  if (processId) {
    form.append('process_id', processId)
  }
  const headers = await authHeaders()
  const response = await apiClient.post<AgentMessage>('/api/v1/agent1/discover', form, { headers })
  return response.data
}

export async function listDiscoveredProcesses(): Promise<ProcessSummary[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessSummary[]>('/api/v1/agent1/processes', { headers })
  return response.data
}

export async function getDiscoveredProcess(processId: string): Promise<ProcessDetail> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessDetail>(`/api/v1/agent1/processes/${processId}`, {
    headers,
  })
  return response.data
}

// --- Processes / Agent 4 pipeline ------------------------------------------

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

export async function startProcess(processId: string): Promise<ProcessStartResponse> {
  const headers = await authHeaders()
  const response = await apiClient.post<ProcessStartResponse>(
    `/api/v1/processes/${processId}/start`,
    {},
    { headers },
  )
  return response.data
}

export async function planResources(
  processId: string,
  payload: {
    task_id: string
    tenant_id: string
    correlation_id?: string
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

export type InvoiceMatchingPayload = {
  invoice_number?: string
  amount?: number
  currency?: string
  vendor?: string
  po_reference?: string
  expected_po_reference?: string
  expected_amount?: number
  expected_currency?: string
  expected_vendor?: string
  expected_invoice_number?: string
  notes?: string
  reference?: string
}

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

// --- Approvals -------------------------------------------------------------

export async function listApprovals(status?: string): Promise<ApprovalRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ApprovalRecord[]>('/api/v1/approvals', {
    headers,
    params: status ? { status } : undefined,
  })
  return response.data
}

export async function getApproval(approvalId: string): Promise<ApprovalRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<ApprovalRecord>(`/api/v1/approvals/${approvalId}`, {
    headers,
  })
  return response.data
}

export async function decideApproval(
  approvalId: string,
  decision: 'approve' | 'reject',
  comments?: string,
  execution?: Record<string, unknown>,
): Promise<ApprovalDecisionResponse> {
  const headers = await authHeaders()
  const response = await apiClient.post<ApprovalDecisionResponse>(
    `/api/v1/approvals/${approvalId}/${decision}`,
    { comments, execution },
    { headers },
  )
  return response.data
}

// --- Exceptions ------------------------------------------------------------

export async function listExceptions(status?: string): Promise<ExceptionRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ExceptionRecord[]>('/api/v1/exceptions', {
    headers,
    params: status ? { status } : undefined,
  })
  return response.data
}

export async function getException(exceptionId: string): Promise<ExceptionRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<ExceptionRecord>(`/api/v1/exceptions/${exceptionId}`, {
    headers,
  })
  return response.data
}

export async function resolveException(
  exceptionId: string,
  resolution_notes: string,
): Promise<{ exception: ExceptionRecord }> {
  const headers = await authHeaders()
  const response = await apiClient.post(
    `/api/v1/exceptions/${exceptionId}/resolve`,
    { resolution_notes },
    { headers },
  )
  return response.data
}

export async function retryException(
  exceptionId: string,
  notes?: string,
): Promise<{ exception: ExceptionRecord }> {
  const headers = await authHeaders()
  const response = await apiClient.post(
    `/api/v1/exceptions/${exceptionId}/retry`,
    { notes },
    { headers },
  )
  return response.data
}

export async function failException(
  exceptionId: string,
  resolution_notes: string,
): Promise<{ exception: ExceptionRecord }> {
  const headers = await authHeaders()
  const response = await apiClient.post(
    `/api/v1/exceptions/${exceptionId}/fail`,
    { resolution_notes },
    { headers },
  )
  return response.data
}

// --- Audit -----------------------------------------------------------------

export async function listAuditLogs(params?: {
  entity_type?: string
  entity_id?: string
  limit?: number
  offset?: number
}): Promise<AuditLogRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<AuditLogRecord[]>('/api/v1/audit', {
    headers,
    params,
  })
  return response.data
}

// --- Agent 2 ---------------------------------------------------------------

export async function listExecutionReceipts(params?: {
  process_id?: string
  status?: string
  limit?: number
}): Promise<ExecutionReceipt[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ExecutionReceipt[]>('/api/v1/agent2/receipts', {
    headers,
    params,
  })
  return response.data
}

export async function getProcessKpis(processId?: string): Promise<Record<string, unknown>> {
  const headers = await authHeaders()
  const response = await apiClient.get<Record<string, unknown>>('/api/v1/agent2/kpis', {
    headers,
    params: processId ? { process_id: processId } : undefined,
  })
  return response.data
}

export async function listOptimizationRecommendations(
  processId?: string,
): Promise<OptimizationRecommendation[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<OptimizationRecommendation[]>(
    '/api/v1/agent2/recommendations',
    {
      headers,
      params: processId ? { process_id: processId } : undefined,
    },
  )
  return response.data
}

export async function decideOptimization(
  recommendationId: string,
  decision: 'approve' | 'reject',
  userId: string,
  notes = '',
): Promise<Record<string, unknown>> {
  const headers = await authHeaders()
  const response = await apiClient.post(
    `/api/v1/agent2/recommendations/${recommendationId}/${decision}`,
    { user_id: userId, notes },
    { headers },
  )
  return response.data
}

export async function listAgent2AuditLogs(limit = 50): Promise<Agent2AuditLog[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<Agent2AuditLog[]>('/api/v1/agent2/audit-logs', {
    headers,
    params: { limit },
  })
  return response.data
}

export default apiClient
