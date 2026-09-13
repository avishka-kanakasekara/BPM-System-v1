"""Structured one-step execution failures. Raised before any mutating tool call."""

from uuid import UUID


class WorkflowStepExecutionError(ValueError):
    error_code = "WORKFLOW_STEP_EXECUTION_ERROR"
    http_status = 422

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        self.error_code = error_code or self.error_code
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {"error_code": self.error_code, "message": str(self)}


class FullWorkflowForbiddenError(WorkflowStepExecutionError):
    error_code = "FULL_WORKFLOW_EXECUTION_FORBIDDEN"
    http_status = 403


class CrossTenantDeniedError(WorkflowStepExecutionError):
    error_code = "CROSS_TENANT_DENIED"
    http_status = 403


class PlanNotExecutableError(WorkflowStepExecutionError):
    error_code = "PLAN_NOT_EXECUTABLE"
    http_status = 409


class HumanApprovalRequiredError(WorkflowStepExecutionError):
    error_code = "HUMAN_APPROVAL_REQUIRED"
    http_status = 409


class DependencyNotCompletedError(WorkflowStepExecutionError):
    error_code = "DEPENDENCY_NOT_COMPLETED"
    http_status = 409


class StepNotExecutableError(WorkflowStepExecutionError):
    error_code = "STEP_NOT_EXECUTABLE"
    http_status = 409


class MissingRequiredExecutionContextError(WorkflowStepExecutionError):
    error_code = "MISSING_REQUIRED_EXECUTION_CONTEXT"
    http_status = 422


class ConflictingExecutionInputError(WorkflowStepExecutionError):
    error_code = "CONFLICTING_EXECUTION_INPUT"
    http_status = 422


class InvalidToolInputError(WorkflowStepExecutionError):
    error_code = "INVALID_TOOL_INPUT"
    http_status = 422


class NotAuthorizedError(WorkflowStepExecutionError):
    error_code = "NOT_AUTHORIZED"
    http_status = 403


class StepAlreadyInProgressError(WorkflowStepExecutionError):
    error_code = "STEP_IN_PROGRESS"
    http_status = 409


class WorkflowStepIdRequiredError(WorkflowStepExecutionError):
    error_code = "WORKFLOW_STEP_REQUIRED"
    http_status = 422


class UnknownWorkflowStepError(WorkflowStepExecutionError):
    error_code = "WORKFLOW_STEP_NOT_FOUND"
    http_status = 404

    def __init__(self, step_id: UUID) -> None:
        super().__init__(f"Unknown workflow step: {step_id}")
        self.step_id = step_id


class CommunicationRecipientInvalidError(WorkflowStepExecutionError):
    error_code = "COMMUNICATION_RECIPIENT_INVALID"
    http_status = 422


class CompanyDirectoryUnavailableError(WorkflowStepExecutionError):
    error_code = "COMPANY_DIRECTORY_UNAVAILABLE"
    http_status = 503
