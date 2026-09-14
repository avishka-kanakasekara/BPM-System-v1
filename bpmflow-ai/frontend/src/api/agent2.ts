import { apiClient, authHeaders } from './http'
import type { ExecutionReceipt } from '../types/api'

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

/** Agent 2 analytics KPIs — not process monitoring GET /processes/{id}/kpis. */
export async function getProcessKpis(processId?: string): Promise<Record<string, unknown>> {
  const headers = await authHeaders()
  const response = await apiClient.get<Record<string, unknown>>('/api/v1/agent2/kpis', {
    headers,
    params: processId ? { process_id: processId } : undefined,
  })
  return response.data
}

/** Agent 2 execution-optimization suggestions. Not process TO-BE recommendations. */
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

/**
 * Isolated legacy Agent 2 execute-by-tool-name.
 * Product UI must not use this as a free-form RPA launcher.
 * Prefer executeWorkflowStep in api/workflows.ts.
 */
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
