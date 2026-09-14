import { apiClient, authHeaders } from './http'
import type {
  WorkflowPlanRecord,
  WorkflowPlanValidationResult,
  WorkflowStepExecutionResult,
  WorkflowStepRecord,
} from '../types/api'

export async function createWorkflowPlan(payload: {
  process_id: string
  source_process_context_schema_version?: string
  source_process_context_ref?: string
}): Promise<WorkflowPlanRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowPlanRecord>('/api/v1/workflows', payload, {
    headers,
  })
  return response.data
}

export async function getWorkflowPlan(workflowPlanId: string): Promise<WorkflowPlanRecord> {
  const headers = await authHeaders()
  const response = await apiClient.get<WorkflowPlanRecord>(`/api/v1/workflows/${workflowPlanId}`, {
    headers,
  })
  return response.data
}

export async function listWorkflowSteps(workflowPlanId: string): Promise<WorkflowStepRecord[]> {
  const headers = await authHeaders()
  const response = await apiClient.get<WorkflowStepRecord[]>(
    `/api/v1/workflows/${workflowPlanId}/steps`,
    { headers },
  )
  return response.data
}

export async function addWorkflowStep(
  workflowPlanId: string,
  payload: Record<string, unknown>,
): Promise<WorkflowStepRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowStepRecord>(
    `/api/v1/workflows/${workflowPlanId}/steps`,
    payload,
    { headers },
  )
  return response.data
}

export async function validateWorkflowPlan(
  workflowPlanId: string,
): Promise<WorkflowPlanValidationResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowPlanValidationResult>(
    `/api/v1/workflows/${workflowPlanId}/validate`,
    {},
    { headers },
  )
  return response.data
}

/** Approver or admin. */
export async function activateWorkflowPlan(workflowPlanId: string): Promise<WorkflowPlanRecord> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowPlanRecord>(
    `/api/v1/workflows/${workflowPlanId}/activate`,
    {},
    { headers },
  )
  return response.data
}

/** Agent 2 one authorized WorkflowStep. Tool name is not caller-authoritative. */
export async function executeWorkflowStep(
  workflowPlanId: string,
  workflowStepId: string,
  payload: {
    process_id: string
    process_context_ref?: string
    trace_id?: string
    idempotency_key?: string
    parameters?: Record<string, unknown>
  },
): Promise<WorkflowStepExecutionResult> {
  const headers = await authHeaders()
  const response = await apiClient.post<WorkflowStepExecutionResult>(
    `/api/v1/workflows/${workflowPlanId}/steps/${workflowStepId}/execute`,
    payload,
    { headers },
  )
  return response.data
}
