/**
 * Frontend types aligned with backend Pydantic schemas and HTTP routes.
 * Field names are taken from backend source — do not invent properties.
 *
 * Process stages: import WorkflowStage from this file or from lib/processStages
 * (same union; processStages is the enumerations/labels source of truth).
 */

export type { WorkflowStage } from '../lib/processStages'
import type { WorkflowStage } from '../lib/processStages'

export type AppRole = 'requester' | 'approver' | 'admin'

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
  tenant_id?: string | null
  process_context?: ProcessContext | Record<string, unknown> | null
  designated_approver_id?: string | null
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

/**
 * POST .../complete-invoice-matching body (backend InvoiceMatchingCompleteRequest).
 * Matching truth is the persisted Invoice vs PO. expected_* is not source of truth.
 * @deprecated Do not send expected_* from the product UI.
 */
export type InvoiceMatchingPayload = {
  invoice_number?: string
  amount?: number
  currency?: string
  vendor?: string
  po_reference?: string
  /** @deprecated Not matching truth. */
  expected_po_reference?: string
  /** @deprecated Not matching truth. */
  expected_amount?: number
  /** @deprecated Not matching truth. */
  expected_currency?: string
  /** @deprecated Not matching truth. */
  expected_vendor?: string
  /** @deprecated Not matching truth. */
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

/**
 * POST /processes/{id}/advance response.advance field.
 * `autonomous_actions` is the backend JSON key for Agent 4 recorded stage transitions.
 * It is not unsupervised BPM execution.
 */
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
  tenant_id?: string | null
  workflow_plan_id?: string | null
  workflow_step_id?: string | null
  exception_code?: string | null
  title?: string | null
  severity: string
  type: string
  description: string
  status: string
  assigned_to?: string | null
  assigned_employee_id?: string | null
  resolved_by_employee_id?: string | null
  source_agent?: string | null
  source_operation?: string | null
  evidence_refs?: string[]
  details?: Record<string, unknown>
  resolution_notes?: string | null
  created_at: string
  updated_at?: string | null
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

export type FactSource =
  | 'authenticated'
  | 'extracted_evidence'
  | 'company_repository'
  | 'policy_repository'
  | 'agent_derived'
  | 'unspecified'

export type EvidenceItem = {
  evidence_id: string
  document_id?: string | null
  source?: string | null
  type?: string | null
  page?: number | null
  section?: string | null
  field?: string | null
}

export type EvidenceReference = EvidenceItem

export type RequesterIdentity = {
  user_id?: string | null
  employee_resource_id?: string | null
  name?: string | null
  email?: string | null
  department?: string | null
  identity_mapped?: boolean
}

export type ApproverIdentity = {
  user_id?: string | null
  employee_resource_id?: string | null
  role?: string | null
  email?: string | null
  approval_id?: string | null
}

export type PurchaseItem = {
  description?: string | null
  quantity?: string | number | null
  unit_amount?: string | number | null
  currency?: string | null
}

export type PurchaseFacts = {
  description?: string | null
  amount?: string | number | null
  currency?: string | null
  vendor_id?: string | null
  vendor_name?: string | null
  cost_centre?: string | null
  purchase_request_id?: string | null
  items?: PurchaseItem[]
  amount_source?: FactSource
}

export type BudgetFacts = {
  budget_id?: string | null
  allocated_amount?: string | number | null
  used_amount?: string | number | null
  available_amount?: string | number | null
  currency?: string | null
  source?: FactSource
}

export type QuotationFact = {
  quotation_id: string
  vendor?: string | null
  amount?: string | number | null
  currency?: string | null
  document_id?: string | null
  evidence_id?: string | null
  status?: string | null
  source?: FactSource
}

export type PolicyRefs = {
  policy_ids?: string[]
  policy_version?: string | null
  evidence_ids?: string[]
}

export type RiskSnapshot = {
  categories?: string[]
  risk_level?: string | null
  findings?: Record<string, unknown>[]
  evidence_ids?: string[]
}

export type DiscoveryActivity = {
  name: string
  actor?: string | null
  system?: string | null
}

export type DiscoveryDependency = {
  predecessor: string
  successor: string
}

export type DiscoverySummary = {
  discovery_status?: string | null
  message_id?: string | null
  trace_id?: string | null
  activities?: DiscoveryActivity[]
  dependencies?: DiscoveryDependency[]
  gaps?: string[]
}

export type ProcessContext = {
  process_id: string
  tenant_id?: string | null
  request_id?: string
  schema_version?: string
  requester?: RequesterIdentity
  purchase?: PurchaseFacts
  budget?: BudgetFacts
  quotations?: QuotationFact[]
  evidence?: EvidenceItem[]
  approver?: ApproverIdentity
  policy?: PolicyRefs
  risk?: RiskSnapshot
  discovery?: DiscoverySummary
  updated_at?: string | null
}

export type WorkflowPlanStatus =
  | 'DRAFT'
  | 'READY'
  | 'ACTIVE'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'SUPERSEDED'
  | 'EXCEPTION'

export type WorkflowStepType =
  | 'HUMAN_TASK'
  | 'APPROVAL'
  | 'SYSTEM_ACTION'
  | 'COMMUNICATION'
  | 'VALIDATION'
  | 'DOCUMENT_REVIEW'
  | 'RESOURCE_ALLOCATION'
  | 'EXCEPTION_HANDLING'

export type WorkflowStepStatus =
  | 'PENDING'
  | 'READY'
  | 'WAITING_DEPENDENCY'
  | 'WAITING_HUMAN_APPROVAL'
  | 'AUTHORIZED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'FAILED'
  | 'SKIPPED'
  | 'CANCELLED'
  | 'EXCEPTION'

export type WorkflowEvidenceRef = {
  evidence_id: string
  document_id?: string | null
  kind?: string | null
}

export type WorkflowPolicyRef = {
  policy_id: string
  policy_version?: string | null
}

export type WorkflowStepRecord = {
  id: string
  tenant_id: string
  workflow_plan_id: string
  step_key: string
  sequence: number
  name: string
  description?: string | null
  step_type: WorkflowStepType | string
  status: WorkflowStepStatus | string
  responsible_employee_id?: string | null
  responsible_resource_id?: string | null
  responsible_role_id?: string | null
  responsible_department_id?: string | null
  assignment_unresolved?: boolean
  unresolved_reason?: string | null
  depends_on_step_keys?: string[]
  required_action?: string | null
  required_tool_category?: string | null
  inputs?: Record<string, unknown>
  expected_outputs?: Record<string, unknown>
  evidence_refs?: WorkflowEvidenceRef[]
  policy_refs?: WorkflowPolicyRef[]
  risk_level?: string | null
  approval_required?: boolean
  approval_type?: string | null
  recipient_employee_ids?: string[]
  created_at?: string | null
  updated_at?: string | null
}

export type WorkflowPlanRecord = {
  id: string
  tenant_id: string
  process_id: string
  version: number
  status: WorkflowPlanStatus | string
  created_by_agent?: string
  source_process_context_schema_version?: string | null
  source_process_context_ref?: string | null
  steps?: WorkflowStepRecord[]
  created_at?: string | null
  updated_at?: string | null
}

export type ValidationIssue = {
  code: string
  message: string
  step_key?: string | null
}

export type WorkflowPlanValidationResult = {
  valid: boolean
  issues: ValidationIssue[]
}

export type PlanningIssue = {
  code: string
  message: string
  blocking?: boolean
  step_key?: string | null
}

export type WorkflowPlanningResult = {
  process_id: string
  tenant_id: string
  workflow_plan_id?: string | null
  version?: number | null
  status?: string | null
  execution_ready?: boolean
  structurally_valid?: boolean
  steps?: WorkflowStepRecord[]
  issues?: PlanningIssue[]
  plan?: WorkflowPlanRecord | null
  allocations?: Record<string, unknown>
}

export type WorkflowStepExecutionResult = {
  execution_status: string
  workflow_plan_id: string
  workflow_step_id: string
  process_id: string
  action_code?: string | null
  tool_name?: string | null
  implementation_key?: string | null
  receipt_id?: string | null
  step_status: string
  result?: Record<string, unknown>
  error_code?: string | null
  error_message?: string | null
  trace_id?: string | null
  idempotency_key?: string | null
  duplicate?: boolean
}

export type EmployeeRecord = {
  employee_id: string
  tenant_id: string
  employee_number: string
  full_name: string
  email: string
  phone?: string | null
  department_id: string
  role_id: string
  manager_employee_id?: string | null
  status: 'active' | 'inactive' | string
  resource_id?: string | null
  user_id?: string | null
  skill_codes?: string[]
  is_available?: boolean
  current_workload_pct?: string | number | null
  max_workload_pct?: string | number | null
}

export type DepartmentRecord = {
  department_id: string
  tenant_id: string
  name: string
  code: string
  manager_employee_id?: string | null
  status?: string
}

export type RoleRecord = {
  role_id: string
  tenant_id: string
  name: string
  code: string
  description?: string | null
  department_id?: string | null
  status?: string
}

export type ApproverCandidate = {
  employee_id: string
  employee_number: string
  full_name: string
  email: string
  role_name: string
  role_code: string
  department_code?: string | null
  authority_code?: string | null
  approval_type: string
  max_amount: string | number
  currency: string
  resource_id?: string | null
}

export type SodComparison = {
  status: 'SAME_PERSON' | 'DISTINCT' | 'APPROVER_NOT_RESOLVED' | string
  requester_employee_id?: string | null
  approver_employee_id?: string | null
  same_person?: boolean
}

export type VendorRecord = {
  vendor_id: string
  tenant_id: string
  vendor_code: string
  legal_name: string
  status: 'active' | 'inactive' | string
  phone?: string | null
  website?: string | null
  notes?: string | null
}

export type QuotationItemRecord = {
  item_id: string
  tenant_id: string
  quotation_id: string
  description: string
  quantity: string | number
  unit_price: string | number
  line_total: string | number
}

export type QuotationRecord = {
  quotation_id: string
  tenant_id: string
  quotation_number: string
  vendor_id: string
  process_id: string
  currency: string
  subtotal: string | number
  tax?: string | number
  total: string | number
  status: string
  quotation_date?: string | null
  evidence_id?: string | null
  document_id?: string | null
  workflow_step_id?: string | null
  items?: QuotationItemRecord[]
}

export type PurchaseOrderItemRecord = {
  item_id: string
  tenant_id: string
  purchase_order_id: string
  description: string
  quantity: string | number
  unit_price: string | number
  line_total: string | number
  source_quotation_item_id?: string | null
}

export type PurchaseOrderRecord = {
  purchase_order_id: string
  tenant_id: string
  po_number: string
  process_id: string
  vendor_id: string
  currency: string
  subtotal: string | number
  tax?: string | number
  total: string | number
  status: string
  workflow_plan_id?: string | null
  workflow_step_id?: string | null
  created_by?: string | null
  selected_quotation_id?: string | null
  notes?: string | null
  items?: PurchaseOrderItemRecord[]
  created_at?: string | null
}

export type InvoiceItemRecord = {
  item_id: string
  tenant_id: string
  invoice_id: string
  description: string
  quantity: string | number
  unit_price: string | number
  line_total: string | number
  purchase_order_item_id?: string | null
}

export type InvoiceRecord = {
  invoice_id: string
  tenant_id: string
  invoice_number: string
  vendor_id: string
  purchase_order_id: string
  process_id: string
  currency: string
  subtotal: string | number
  tax?: string | number
  total: string | number
  status: string
  invoice_date?: string | null
  received_at?: string | null
  evidence_id?: string | null
  document_id?: string | null
  match_result?: Record<string, unknown>
  workflow_step_id?: string | null
  items?: InvoiceItemRecord[]
}

export type InvoiceMatchResultRecord = {
  invoice_id: string
  purchase_order_id: string
  process_id: string
  tenant_id: string
  status: string
  matched: boolean
  discrepancy_codes?: string[]
  discrepancy_details?: string[]
  matched_amount?: string | number | null
  invoice_amount?: string | number | null
  po_amount?: string | number | null
  currency?: string | null
  vendor_match?: boolean
  line_match?: boolean
  evidence_refs?: string[]
  trace_id?: string | null
  amount_tolerance?: string
}

/** Alias matching the procurement InvoiceMatchResultRecord schema. */
export type InvoiceMatchResult = InvoiceMatchResultRecord

export type TimelineEvent = {
  process_id: string
  workflow_plan_id?: string | null
  workflow_step_id?: string | null
  event_type: string
  timestamp: string
  actor?: string | null
  status?: string | null
  trace_id?: string | null
  evidence_ref?: string | null
}

export type BottleneckCandidate = {
  workflow_step_id?: string | null
  step: string
  step_type?: string | null
  average_duration_seconds?: string | number | null
  average_wait_seconds?: string | number | null
  failure_count?: number
  exception_count?: number
  reason?: string[]
}

export type ExceptionAnalytics = {
  total_exceptions?: number
  open_exceptions?: number
  resolved_exceptions?: number
  exceptions_by_code?: Record<string, number>
  exceptions_by_workflow_step?: Record<string, number>
  exception_rate_per_process?: string | number | null
  most_frequent_exception?: string | null
}

export type KpiReport = {
  tenant_id: string
  process_id?: string | null
  window_start?: string | null
  window_end?: string | null
  window_convention?: string
  total_processes?: number
  completed_processes?: number
  exception_processes?: number
  active_processes?: number
  completion_rate?: string | number | null
  exception_rate?: string | number | null
  average_completion_time_seconds?: string | number | null
  average_step_duration_seconds?: string | number | null
  average_human_wait_time_seconds?: string | number | null
  workflow_step_success_rate?: string | number | null
  workflow_step_failure_rate?: string | number | null
  total_exceptions?: number
  exceptions_by_code?: Record<string, number>
  bottleneck_steps?: BottleneckCandidate[]
  insufficient_evidence?: boolean
}

export type ProcessMonitoringReport = {
  process_id: string
  tenant_id: string
  state: string
  status: string
  started_at?: string | null
  completed_at?: string | null
  duration_seconds?: string | number | null
  timeline?: TimelineEvent[]
  steps?: Record<string, unknown>[]
  exceptions?: Record<string, unknown>[]
  kpis: KpiReport
  bottlenecks?: BottleneckCandidate[]
  exception_analytics?: ExceptionAnalytics
}

export type RecommendationEvidence = {
  workflow_step_id?: string | null
  field: string
  value: unknown
  source: string
}

export type TobeRecommendationRecord = {
  id: string
  tenant_id: string
  process_id?: string | null
  workflow_plan_id?: string | null
  recommendation_type: string
  title: string
  description: string
  reason: string
  evidence?: RecommendationEvidence[]
  kpi_snapshot?: Record<string, unknown>
  expected_benefit?: string | null
  risk?: string | null
  confidence?: string | number | null
  status: string
  fingerprint: string
  created_at: string
  reviewed_at?: string | null
  reviewed_by?: string | null
  activates_workflow?: boolean
  policy_status?: string | null
}

export type ToolRegistryRecord = {
  id: string
  tenant_id: string
  tool_name: string
  display_name?: string | null
  description?: string | null
  tool_category: string
  action_code: string
  implementation_key: string
  version?: string
  enabled?: boolean
  requires_authorization?: boolean
  allowed_step_types?: string[]
  required_permissions?: string[]
  input_schema?: Record<string, unknown>
  output_schema?: Record<string, unknown>
  configuration?: Record<string, unknown>
  agent2_tool_name?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type SearchHit = {
  document_id: string
  chunk_id: string
  page?: number | null
  score: number
  text: string
  snippet: string
  document_version?: string | null
  filename?: string | null
  document_type?: string | null
  source?: string | null
  section?: string | null
}

export type DocumentIngestResponse = {
  document_id: string
  tenant_id: string
  filename: string
  document_type?: string | null
  source?: string | null
  version: string
  is_active: boolean
  content_hash: string
  parse_status: string
  parse_failure?: string | null
  chunk_count: number
  reused?: boolean
}

export type EvidenceChunk = {
  chunk_id: string
  document_id: string
  tenant_id: string
  page?: number | null
  chunk_index?: number
  text: string
  document_version?: string | null
  filename?: string | null
  document_type?: string | null
  source?: string | null
  section?: string | null
}

export type DemoHealthPayload = {
  env: string
  debug: boolean
  mock_llm: boolean
  gemini_offline: boolean
  email_dry_run: boolean
  persistence_mode: string
  supabase_url_configured: boolean
  jwt_secret_configured: boolean
  database_url_configured: boolean
  gemini_configured: boolean
  allowed_file_types: string[]
  max_upload_mb: number
  tool_registry_allowlist_size: number
  migrations_on_disk: string[]
  python_runner_migrations: string[]
  migration_0024_on_disk: boolean
  note: string
}
