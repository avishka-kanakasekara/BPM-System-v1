/**
 * Compatibility barrel. New code should import from `src/api/*`.
 * Implementations live under `src/api/` and match Phases 1–13 HTTP routes.
 */
export { apiClient, apiErrorMessage, authHeaders, registerUnauthorizedHandler } from '../api/http'
export { default } from '../api/http'

export * from '../api/auth'
export * from '../api/agent1'
export * from '../api/processes'
export * from '../api/workflows'
export * from '../api/agent2'
export * from '../api/governance'
export * from '../api/directory'
export * from '../api/monitoring'
export * from '../api/policies'

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
