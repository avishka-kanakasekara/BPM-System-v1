"""Controlled Tool Registry enumerations."""

from enum import StrEnum

from app.agents.agent4_orchestrator.workflow_plan.constants import WorkflowStepType


class ToolCategory(StrEnum):
    COMMUNICATION = "COMMUNICATION"
    APPROVAL = "APPROVAL"
    PROCUREMENT = "PROCUREMENT"
    TASK = "TASK"
    DOCUMENT = "DOCUMENT"
    VALIDATION = "VALIDATION"
    SYSTEM = "SYSTEM"
    RESOURCE = "RESOURCE"
    NOTIFICATION = "NOTIFICATION"


class ToolActionCode(StrEnum):
    CREATE_TASK = "CREATE_TASK"
    UPDATE_TASK = "UPDATE_TASK"
    SEND_EMAIL = "SEND_EMAIL"
    SEND_REMINDER = "SEND_REMINDER"
    CREATE_PURCHASE_ORDER = "CREATE_PURCHASE_ORDER"
    REQUEST_QUOTATION = "REQUEST_QUOTATION"
    UPDATE_PROCUREMENT_RECORD = "UPDATE_PROCUREMENT_RECORD"
    ESCALATE = "ESCALATE"
    CREATE_EXCEPTION = "CREATE_EXCEPTION"
    GET_PROCESS_HISTORY = "GET_PROCESS_HISTORY"
    GET_TASK_HISTORY = "GET_TASK_HISTORY"
    CALCULATE_KPI = "CALCULATE_KPI"
    MATCH_INVOICE = "MATCH_INVOICE"


ALLOWED_STEP_TYPES = frozenset(item.value for item in WorkflowStepType)

SECRET_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "private_key",
    "privatekey",
    "client_secret",
    "smtp",
    "oauth",
    "access_token",
    "refresh_token",
    "authorization",
)
