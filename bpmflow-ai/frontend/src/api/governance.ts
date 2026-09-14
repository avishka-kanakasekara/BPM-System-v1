import { apiClient, authHeaders } from './http'
import type {
  ApprovalDecisionResponse,
  ApprovalRecord,
  AuditLogRecord,
  ExceptionRecord,
} from '../types/api'

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

/** Backend supports approve and reject only (no request-changes route). */
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
