"""Resolve communication recipients from Company Directory employee IDs."""

from __future__ import annotations

from uuid import UUID

from app.core.logging import get_logger

from .exceptions import (
    CommunicationRecipientInvalidError,
    CompanyDirectoryUnavailableError,
    CrossTenantDirectoryError,
    DirectoryError,
    EmployeeNotFoundError,
    MissingCompanyEmailError,
)
from .service import CompanyDirectoryService

logger = get_logger(__name__)


def resolve_verified_recipient_emails(
    *,
    tenant_id: UUID,
    employee_ids: list[UUID],
    directory: CompanyDirectoryService,
    workflow_plan_id: UUID | None = None,
    workflow_step_id: UUID | None = None,
    process_id: UUID | None = None,
    trace_id: str | None = None,
) -> list[str]:
    """Resolve every recipient independently. Never omit a failed lookup."""
    if not employee_ids:
        raise CommunicationRecipientInvalidError(
            "recipient_employee_ids are required for communication"
        )
    emails: list[str] = []
    for employee_id in employee_ids:
        try:
            email = directory.require_email_for_employee(
                tenant_id=tenant_id, employee_id=employee_id
            )
        except DirectoryError:
            logger.info(
                "company_directory_email_lookup_failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "employee_id": str(employee_id),
                    "workflow_plan_id": None if workflow_plan_id is None else str(workflow_plan_id),
                    "workflow_step_id": None if workflow_step_id is None else str(workflow_step_id),
                    "process_id": None if process_id is None else str(process_id),
                    "trace_id": trace_id,
                    "lookup_result": "failed",
                },
            )
            raise
        emails.append(email)
        logger.info(
            "company_directory_email_lookup",
            extra={
                "tenant_id": str(tenant_id),
                "employee_id": str(employee_id),
                "workflow_plan_id": None if workflow_plan_id is None else str(workflow_plan_id),
                "workflow_step_id": None if workflow_step_id is None else str(workflow_step_id),
                "process_id": None if process_id is None else str(process_id),
                "trace_id": trace_id,
                "lookup_result": "ok",
            },
        )
    return emails


def map_directory_error(exc: DirectoryError) -> DirectoryError:
    if isinstance(
        exc,
        (
            CommunicationRecipientInvalidError,
            CompanyDirectoryUnavailableError,
            CrossTenantDirectoryError,
            EmployeeNotFoundError,
            MissingCompanyEmailError,
        ),
    ):
        return exc
    return CommunicationRecipientInvalidError(str(exc), error_code=exc.error_code)
