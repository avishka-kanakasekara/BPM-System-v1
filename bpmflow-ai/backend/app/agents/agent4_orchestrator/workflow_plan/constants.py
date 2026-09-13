"""Controlled WorkflowPlan / WorkflowStep enumerations."""

from enum import StrEnum

CREATED_BY_AGENT4 = "agent4"


class WorkflowPlanStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    EXCEPTION = "EXCEPTION"


class WorkflowStepType(StrEnum):
    HUMAN_TASK = "HUMAN_TASK"
    APPROVAL = "APPROVAL"
    SYSTEM_ACTION = "SYSTEM_ACTION"
    COMMUNICATION = "COMMUNICATION"
    VALIDATION = "VALIDATION"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    RESOURCE_ALLOCATION = "RESOURCE_ALLOCATION"
    EXCEPTION_HANDLING = "EXCEPTION_HANDLING"


class WorkflowStepStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
    WAITING_HUMAN_APPROVAL = "WAITING_HUMAN_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"
    EXCEPTION = "EXCEPTION"


HUMAN_STEP_TYPES = frozenset(
    {
        WorkflowStepType.HUMAN_TASK,
        WorkflowStepType.APPROVAL,
        WorkflowStepType.DOCUMENT_REVIEW,
        WorkflowStepType.COMMUNICATION,
        WorkflowStepType.VALIDATION,
    }
)

TOOL_CATEGORY_REQUIRED_TYPES = frozenset(
    {
        WorkflowStepType.SYSTEM_ACTION,
        WorkflowStepType.COMMUNICATION,
        WorkflowStepType.RESOURCE_ALLOCATION,
    }
)

MUTABLE_PLAN_STATUSES = frozenset(
    {
        WorkflowPlanStatus.DRAFT,
        WorkflowPlanStatus.READY,
        WorkflowPlanStatus.EXCEPTION,
    }
)
