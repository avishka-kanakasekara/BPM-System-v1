"""WorkflowPlan errors. Missing people stay explicit — never invented."""

from uuid import UUID


class WorkflowPlanError(ValueError):
    error_code = "WORKFLOW_PLAN_ERROR"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        self.error_code = error_code or self.error_code
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {"error_code": self.error_code, "message": str(self)}


class WorkflowPlanNotFoundError(KeyError):
    def __init__(self, workflow_plan_id: UUID) -> None:
        self.workflow_plan_id = workflow_plan_id
        super().__init__(f"Unknown workflow plan: {workflow_plan_id}")


class WorkflowStepNotFoundError(KeyError):
    def __init__(self, step_key: str) -> None:
        self.step_key = step_key
        super().__init__(f"Unknown workflow step: {step_key}")


class PlanNotMutableError(WorkflowPlanError):
    error_code = "PLAN_NOT_MUTABLE"


class DuplicateStepKeyError(WorkflowPlanError):
    error_code = "DUPLICATE_STEP_KEY"


class DuplicateDependencyError(WorkflowPlanError):
    error_code = "DUPLICATE_DEPENDENCY"


class CrossTenantWorkflowError(WorkflowPlanError):
    error_code = "CROSS_TENANT_DENIED"
