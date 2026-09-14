"""Build tool parameters from ProcessContext and WorkflowStep. Never invent facts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.agents.agent2_execution.workflow_step.exceptions import (
    ConflictingExecutionInputError,
    MissingRequiredExecutionContextError,
    WorkflowStepExecutionError,
)
from app.company_directory.communication import resolve_verified_recipient_emails
from app.company_directory.exceptions import DirectoryError
from app.company_directory.service import CompanyDirectoryService
from app.process_context.schemas import ProcessContext
from app.agents.agent4_orchestrator.workflow_plan.schemas import WorkflowStepRecord


_VERIFIED_KEYS = ("amount", "currency", "vendor_id", "vendor")
_COMMUNICATION_ACTIONS = frozenset({"SEND_EMAIL", "SEND_REMINDER", "NOTIFY", "COMMUNICATE"})


def _decimal_equal(left: Any, right: Any) -> bool:
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except Exception:
        return str(left).strip() == str(right).strip()


def reject_conflicting_overrides(
    *,
    context: ProcessContext,
    caller_parameters: dict[str, Any],
) -> None:
    purchase = context.purchase
    if "amount" in caller_parameters and purchase.amount is not None:
        if not _decimal_equal(caller_parameters["amount"], purchase.amount):
            raise ConflictingExecutionInputError(
                "Caller amount conflicts with verified ProcessContext.purchase.amount"
            )
    if "currency" in caller_parameters and purchase.currency:
        if str(caller_parameters["currency"]).strip().upper() != purchase.currency.strip().upper():
            raise ConflictingExecutionInputError(
                "Caller currency conflicts with verified ProcessContext.purchase.currency"
            )
    caller_vendor = caller_parameters.get("vendor_id") or caller_parameters.get("vendor")
    if caller_vendor and purchase.vendor_id:
        if str(caller_vendor).strip() != str(purchase.vendor_id).strip():
            raise ConflictingExecutionInputError(
                "Caller vendor conflicts with verified ProcessContext.purchase.vendor_id"
            )
    if "recipient" in caller_parameters or "recipient_email" in caller_parameters:
        raise ConflictingExecutionInputError(
            "Caller cannot override communication recipients; use WorkflowStep recipient_employee_ids"
        )


def build_tool_parameters(
    *,
    context: ProcessContext,
    step: WorkflowStepRecord,
    process_id: UUID,
    task_id: str,
    directory: CompanyDirectoryService | None = None,
) -> dict[str, Any]:
    purchase = context.purchase
    params: dict[str, Any] = {
        "process_id": str(process_id),
        "task_id": task_id,
        "process_context_ref": str(context.process_id),
        "workflow_plan_id": str(step.workflow_plan_id),
        "workflow_step_id": str(step.id),
        "tenant_id": str(step.tenant_id),
    }
    action = (step.required_action or "").strip().upper()
    if action == "CREATE_PURCHASE_ORDER":
        vendor_id = purchase.vendor_id
        if vendor_id in (None, "") and purchase.vendor_name and context.tenant_id is not None:
            try:
                from app.procurement.exceptions import VendorNotFoundError
                from app.procurement.service import get_procurement

                vendor_id = str(
                    get_procurement().resolve_vendor(
                        tenant_id=context.tenant_id, vendor_ref=str(purchase.vendor_name)
                    ).vendor_id
                )
            except VendorNotFoundError:
                vendor_id = None
        missing = [
            name
            for name, value in (
                ("purchase.amount", purchase.amount),
                ("purchase.currency", purchase.currency),
                ("purchase.vendor_id", vendor_id),
            )
            if value in (None, "")
        ]
        if missing:
            raise MissingRequiredExecutionContextError(
                f"Missing required execution context: {', '.join(missing)}"
            )
        params["amount"] = float(purchase.amount)
        params["currency"] = str(purchase.currency).strip().upper()
        params["vendor_id"] = str(vendor_id)
        params["items_summary"] = purchase.description or ""
        params["notes"] = f"workflow_step:{step.step_key}"
        if context.budget.available_amount is not None:
            params["budget_available"] = float(context.budget.available_amount)
        if purchase.items:
            params["items"] = [
                {
                    "description": item.description or purchase.description or "Purchase request item",
                    "quantity": float(item.quantity or 1),
                    "unit_price": float(
                        item.unit_amount
                        if item.unit_amount is not None
                        else (
                            purchase.amount / (item.quantity or 1)
                            if purchase.amount is not None and (item.quantity or 1)
                            else purchase.amount
                        )
                    ),
                }
                for item in purchase.items
            ]
        min_quotes = (step.inputs or {}).get("min_quotations")
        if min_quotes not in (None, ""):
            params["min_quotations"] = int(min_quotes)
        if context.quotations:
            params["quotation_facts"] = [fact.model_dump(mode="json") for fact in context.quotations]
    if action == "MATCH_INVOICE":
        invoice_id = (step.inputs or {}).get("invoice_id")
        if invoice_id:
            params["invoice_id"] = str(invoice_id)
    communication = bool(step.recipient_employee_ids) or action in _COMMUNICATION_ACTIONS
    if communication:
        if directory is None:
            raise WorkflowStepExecutionError(
                "Company directory is required to resolve communication recipients",
                error_code="COMPANY_DIRECTORY_UNAVAILABLE",
            )
        try:
            emails = resolve_verified_recipient_emails(
                tenant_id=step.tenant_id,
                employee_ids=list(step.recipient_employee_ids or []),
                directory=directory,
                workflow_plan_id=step.workflow_plan_id,
                workflow_step_id=step.id,
                process_id=process_id,
            )
        except DirectoryError as exc:
            raise WorkflowStepExecutionError(str(exc), error_code=exc.error_code) from exc
        params["recipient"] = emails[0]
        params["recipients"] = emails
        params["recipient_employee_ids"] = [str(item) for item in step.recipient_employee_ids]
        params["directory_verified"] = True
        params["directory_verified_emails"] = emails
    for key, value in (step.inputs or {}).items():
        if key in {
            "tool_resolution",
            "amount_ref",
            "currency_ref",
            "vendor_ref",
            "requester_ref",
            "recipient",
            "recipient_email",
            "recipients",
        }:
            continue
        if key in _VERIFIED_KEYS:
            continue
        params.setdefault(key, value)
    return params
