/**
 * API types aligned with backend Pydantic schemas (app/schemas/*, agent4 schemas).
 * Regenerate from OpenAPI: npm run generate:api-types (requires backend on :8000).
 */

export type AppRole = 'requester' | 'approver' | 'admin'

export type WorkflowStage =
  | 'DRAFT'
  | 'DISCOVERING'
  | 'RESOURCE_PLANNING'
  | 'RISK_REVIEW'
  | 'AWAITING_HUMAN_APPROVAL'
  | 'WORKFLOW_EXECUTION'
  | 'INVOICE_MATCHING'
  | 'EXCEPTION'
  | 'COMPLETED'

export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export type CurrentUser = {
  id: string
  email?: string | null
  full_name?: string | null
  role: AppRole
  department?: string | null
  tenant_id?: string | null
}

export type ProcessRecord = {
  id: string
  name: string
  description?: string | null
  process_type: string
  status: string
  current_stage: WorkflowStage
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

export type RiskFinding = {
  risk_level: RiskLevel
  risk_type: string
  description: string
  recommendation: string
  evidence_refs?: string[]
  policy_version?: string | null
  amount?: string | null
  threshold?: string | null
  currency?: string | null
}

export type RiskAssessment = {
  risk_detected: boolean
  overall_risk_level?: RiskLevel | null
  findings: RiskFinding[]
}

export type ApprovalRecord = {
  id: string
  process_id: string
  task_id?: string | null
  requested_by?: string | null
  approver_id?: string | null
  status: ApprovalStatus
  risk_level: RiskLevel
  reason: string
  decision?: ApprovalStatus | null
  comments?: string | null
  created_at: string
  decided_at?: string | null
}

export type WorkflowResult = {
  process_id: string
  current_stage: WorkflowStage
  success: boolean
  message: string
  error_code?: string | null
  error_message?: string | null
  eligible_for_execution?: boolean
  human_approval_required?: boolean
  approval?: ApprovalRecord | null
  risk_assessment?: RiskAssessment | null
  agent_response?: Record<string, unknown> | null
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

export type AdvancementAction = {
  stage: WorkflowStage
  action: string
  guardrail: string
  success: boolean
  message: string
  correlation_id: string
  timestamp: string
}

export type AdvanceProcessResult = {
  process_id: string
  run_id: string
  correlation_id: string
  idempotency_key: string
  status: 'RUNNING' | 'COMPLETED' | 'WAITING_HUMAN' | 'WAITING_INPUT' | 'FAILED'
  from_stage: WorkflowStage
  current_stage: WorkflowStage
  steps_taken: number
  autonomous_actions: AdvancementAction[]
  waiting_for?: string | null
  message: string
  human_approval_required?: boolean
  replayed?: boolean
  last_step?: WorkflowResult | null
  error_code?: string | null
  error_message?: string | null
}

export type AdvanceProcessResponse = {
  process: ProcessRecord
  advancement: AdvanceProcessResult
}

export type ApprovalDecisionResponse = {
  approval: ApprovalRecord
  decision: ApprovalStatus
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
