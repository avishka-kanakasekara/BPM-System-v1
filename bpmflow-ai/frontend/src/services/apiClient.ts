import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import type {
  AdvanceProcessResponse,
  ApprovalDecisionResponse,
  ApprovalRecord,
  AuditLogRecord,
  CurrentUser,
  ExceptionRecord,
  ExecutionReceipt,
  InvoiceMatchingPayload,
  ProcessRecord,
  ProcessStartResponse,
  WorkflowResult,
} from '../types/api'
import { supabase } from './supabaseClient'

export type {
  AppRole,
  AdvancementAction,
  AdvanceProcessResponse,
  AdvanceProcessResult,
  ApprovalDecisionResponse,
  ApprovalRecord,
  ApprovalStatus,
  AuditLogRecord,
  CurrentUser,
  ExceptionRecord,
  ExecutionReceipt,
  InvoiceMatchingPayload,
  ProcessRecord,
  ProcessStartResponse,
  RiskAssessment,
  RiskFinding,
  RiskLevel,
  WorkflowResult,
  WorkflowStage,
} from '../types/api'

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

let unauthorizedHandler: (() => void) | null = null

/** Register a callback for global 401 handling (sign-out + redirect). */
export function registerUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler
}

apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  if (config.data instanceof FormData) {
    config.headers.delete('Content-Type')
  } else if (!config.headers.get('Content-Type')) {
    config.headers.set('Content-Type', 'application/json')
  }
  const headers = await authHeaders()
  if (headers.Authorization) {
    config.headers.set('Authorization', headers.Authorization)
  }
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status
    if (status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    return Promise.reject(error)
  },
)

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

// --- Types (agent-specific; shared API types live in src/types/api.ts) ----

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

export type ExecutionReceiptDetail = ExecutionReceipt & {
  execution_id?: string
  receipt_status?: string
  attempt?: number
  started_at?: string
  completed_at?: string
  result?: Record<string, unknown>
  authorization?: { agent4_authorized?: boolean; tool_guard?: string }
  plan_score?: Record<string, unknown>
}

export type Agent2ToolCapability = {
  name: string
  description: string
  category: string
  permission_level: string
  requires_agent4_authorization: boolean
  read_only: boolean
  available: boolean
  required_inputs: string[]
  input_fields: Array<{
    name: string
    type: string
    description: string
    required: boolean
  }>
}

export type Agent2Dashboard = {
  agent: string
  status: string
  process_id?: string | null
  metrics: {
    total_executions: number
    successful: number
    failed: number
    blocked: number
    retrying: number
    success_rate: number
    failure_rate: number
    average_latency_ms: number
    open_exceptions: number
    audit_events: number
  }
  tool_usage: Record<string, number>
  recent_executions: Array<Record<string, unknown>>
  kpis: Record<string, unknown>
  health: string
}

export type Agent2Exception = {
  exception_id: string
  process_id: string
  task_id: string
  category: string
  severity: string
  description: string
  status: string
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

/** Development-only: create a confirmed Supabase user via the backend admin API. */
export async function registerAccount(payload: {
  email: string
  password: string
  full_name?: string
  role?: 'requester' | 'approver' | 'admin'
}): Promise<{ id: string; email: string; confirmed: boolean; role?: string }> {
  const response = await apiClient.post<{
    id: string
    email: string
    confirmed: boolean
    role?: string
  }>('/api/v1/auth/register', payload)
  return response.data
}

/** Development-only: confirm an unconfirmed email so password sign-in works. */
export async function confirmAccountEmail(email: string): Promise<{ ok: boolean }> {
  const response = await apiClient.post<{ ok: boolean }>('/api/v1/auth/confirm-email', { email })
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

export async function getAgent2Dashboard(processId?: string): Promise<Agent2Dashboard> {
  const headers = await authHeaders()
  const response = await apiClient.get<Agent2Dashboard>('/api/v1/agent2/dashboard', {
    headers,
    params: processId ? { process_id: processId } : undefined,
  })
  return response.data
}

export async function listAgent2Tools(): Promise<Agent2ToolCapability[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<Agent2ToolCapability[]>('/api/v1/agent2/tools', {
    headers,
  })
  return response.data
}

export async function getExecutionReceiptDetail(
  receiptId: string,
): Promise<ExecutionReceiptDetail> {
  const headers = await authHeaders()
  const response = await apiClient.get<ExecutionReceiptDetail>(
    `/api/v1/agent2/receipts/${receiptId}`,
    { headers },
  )
  return response.data
}

export async function executeAgent2Tool(payload: {
  process_id: string
  task_id: string
  tool_name: string
  parameters: Record<string, unknown>
  correlation_id?: string
}): Promise<ExecutionReceiptDetail> {
  const headers = await authHeaders()
  const response = await apiClient.post<ExecutionReceiptDetail>(
    '/api/v1/agent2/execute',
    payload,
    { headers },
  )
  return response.data
}

export async function retryAgent2Execution(
  receiptId: string,
  payload: {
    process_id: string
    task_id: string
    tool_name: string
    parameters: Record<string, unknown>
  },
): Promise<ExecutionReceiptDetail> {
  const headers = await authHeaders()
  const response = await apiClient.post<ExecutionReceiptDetail>(
    `/api/v1/agent2/receipts/${receiptId}/retry`,
    payload,
    { headers },
  )
  return response.data
}

export async function listAgent2Exceptions(params?: {
  process_id?: string
  status?: string
  limit?: number
}): Promise<Agent2Exception[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<Agent2Exception[]>('/api/v1/agent2/exceptions', {
    headers,
    params,
  })
  return response.data
}

// --- Company policies (Agent 4 knowledge repository) -----------------------

export type PolicyCategory =
  | 'PROCUREMENT'
  | 'APPROVAL'
  | 'BUDGET'
  | 'AUTHORIZATION'
  | 'SLA'
  | 'SECURITY'
  | 'FINANCE'
  | 'GENERAL'

export type PolicyVersionStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED'

export type PolicyRule = {
  id?: string
  rule_type: string
  operator?: string | null
  threshold_value?: string | null
  currency?: string | null
  required_approval?: string | null
  required_roles?: string[]
  required_evidence?: string[]
  sla_hours?: string | null
  description?: string | null
}

export type PolicyVersionRecord = {
  id: string
  policy_id: string
  tenant_id: string
  version_label: string
  status: PolicyVersionStatus
  document_name: string
  document_type: string
  effective_from: string
  effective_to?: string | null
  uploaded_at: string
  rules: PolicyRule[]
  chunks?: unknown[]
}

export type CompanyPolicyRecord = {
  id: string
  tenant_id: string
  name: string
  category: PolicyCategory
  description?: string | null
  versions: PolicyVersionRecord[]
}

export async function listPolicies(): Promise<CompanyPolicyRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<CompanyPolicyRecord[]>('/api/v1/policies', { headers })
  return response.data
}

export async function uploadPolicy(input: {
  name: string
  category: PolicyCategory
  version_label: string
  description?: string
  document_type?: string
  activate?: boolean
  text_content?: string
  file?: File | null
  effective_from?: string
  effective_to?: string
}): Promise<CompanyPolicyRecord> {
  const headers = await authHeaders()
  const form = new FormData()
  form.append('name', input.name)
  form.append('category', input.category)
  form.append('version_label', input.version_label)
  form.append('document_type', input.document_type || 'txt')
  form.append('activate', String(input.activate ?? true))
  if (input.description) form.append('description', input.description)
  if (input.text_content) form.append('text_content', input.text_content)
  if (input.effective_from) {
    form.append('effective_from', new Date(input.effective_from).toISOString())
  }
  if (input.effective_to) {
    form.append('effective_to', new Date(input.effective_to).toISOString())
  }
  if (input.file) form.append('file', input.file)
  const response = await apiClient.post<CompanyPolicyRecord>('/api/v1/policies', form, {
    headers,
  })
  return response.data
}

export async function activatePolicyVersion(
  policyId: string,
  versionId: string,
): Promise<CompanyPolicyRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<CompanyPolicyRecord>(
    `/api/v1/policies/${policyId}/versions/${versionId}/activate`,
    {},
    { headers },
  )
  return response.data
}

export async function archivePolicyVersion(
  policyId: string,
  versionId: string,
): Promise<CompanyPolicyRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<CompanyPolicyRecord>(
    `/api/v1/policies/${policyId}/versions/${versionId}/archive`,
    {},
    { headers },
  )
  return response.data
}

export default apiClient
