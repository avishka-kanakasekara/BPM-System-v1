import axios, { AxiosRequestConfig } from 'axios'
import { supabase } from './supabaseClient'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_URL,
})

apiClient.interceptors.request.use((config: AxiosRequestConfig) => {
  const headers = config.headers ?? {}
  if (config.data instanceof FormData) {
    if (typeof headers.delete === 'function') {
      headers.delete('Content-Type')
    } else {
      delete (headers as Record<string, unknown>)['Content-Type']
    }
  } else if (!headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }
  config.headers = headers
  return config
})

/** Optional Bearer header from the current Supabase session (never logs the token). */
export async function authHeaders(): Promise<Record<string, string>> {
  if (!supabase) {
    return {}
  }
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
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
  workflow?: {
    process_id: string
    current_stage: string
    success: boolean
    message: string
    error_code?: string | null
    error_message?: string | null
  } | null
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
  agent_response?: Record<string, unknown> | null
}

export async function discoverProcess(files: File[]): Promise<AgentMessage> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  const response = await apiClient.post<AgentMessage>('/api/v1/agent1/discover', form)
  return response.data
}

export async function listDiscoveredProcesses(): Promise<ProcessSummary[]> {
  const response = await apiClient.get<ProcessSummary[]>('/api/v1/agent1/processes')
  return response.data
}

export async function listProcesses(): Promise<ProcessRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ProcessRecord[]>('/api/v1/processes', { headers })
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

export async function startProcess(processId: string) {
  const headers = await authHeaders()
  const response = await apiClient.post(`/api/v1/processes/${processId}/start`, {}, { headers })
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
  reference = '',
): Promise<WorkflowResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowResult>(
    `/api/v1/processes/${processId}/complete-invoice-matching`,
    { reference },
    { headers },
  )
  return response.data
}

export async function listApprovals(status?: string): Promise<ApprovalRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<ApprovalRecord[]>('/api/v1/approvals', {
    headers,
    params: status ? { status } : undefined,
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

export default apiClient
