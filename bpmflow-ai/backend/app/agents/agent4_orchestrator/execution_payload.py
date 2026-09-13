"""Build Agent 2 execution payloads from canonical ProcessContext.

Shared by POST /processes/{id}/execute, process autopilot (Agent 4), and the
post-approval dispatch path. Missing business facts are never invented.
"""

from __future__ import annotations

from typing import Any

from app.agents.agent2_execution.agent.planner_fallback import FULL_TASK_SUITE_TOOL
from app.process_context.exceptions import MissingRequiredContextError
from app.process_context.schemas import ProcessContext
from app.process_context.service import context_from_process_row

from .exceptions import ExecutionEnrichmentError

_PROCUREMENT_TYPES = frozenset(
    {"PROCUREMENT", "PURCHASE", "PO", "PURCHASE_ORDER", "BUY"}
)

_REQUIRED_PROCUREMENT_FIELDS = ("vendor_id", "amount", "currency")

# Legacy single-tool dispatch names upgraded to the workflow suite automatically.
_LEGACY_SUITE_ALIASES = frozenset({"create_po_draft", "execute_task", "execute_po_draft"})


def build_process_execution_metadata(process: Any) -> dict[str, Any]:
    """Merge metadata_json, process_json, and process_context for enrichment."""
    meta = dict(getattr(process, "metadata_json", None) or {})
    process_json = getattr(process, "process_json", None)
    if isinstance(process_json, dict):
        meta = meta | {"process_json": process_json}
    context = getattr(process, "process_context", None)
    if isinstance(context, dict) and context:
        meta = meta | {"process_context": context}
    elif process is not None:
        try:
            meta = meta | {"process_context": context_from_process_row(process).model_dump(mode="json")}
        except Exception:
            pass
    return meta


def _extract_risk_facts(metadata_json: dict[str, Any] | None) -> dict[str, Any]:
    meta = metadata_json or {}
    process_json = meta.get("process_json") if isinstance(meta.get("process_json"), dict) else {}
    analytics = (
        process_json.get("analytics")
        if isinstance(process_json.get("analytics"), dict)
        else {}
    )
    facts = analytics.get("risk_facts")
    return facts if isinstance(facts, dict) else {}


def _context_from_meta(metadata_json: dict[str, Any] | None) -> ProcessContext | None:
    raw = (metadata_json or {}).get("process_context")
    if isinstance(raw, dict) and raw.get("process_id"):
        return ProcessContext.model_validate(raw)
    return None


def _is_procurement(process_type: str | None) -> bool:
    process_type_u = (process_type or "PROCUREMENT").upper()
    if process_type_u in _PROCUREMENT_TYPES or process_type_u.endswith("PROCUREMENT"):
        return True
    return process_type_u in {"GENERAL", "GENERIC", ""}


def _normalize_workflow_tool_name(tool_name: str | None) -> str | None:
    """Reject bulk suite names. A specific allow-listed tool may still be named."""
    clean = (tool_name or "").strip().lower()
    if not clean or clean in _LEGACY_SUITE_ALIASES or clean == FULL_TASK_SUITE_TOOL:
        return None
    return clean


def _resolve_procurement_fields(
    *,
    params: dict[str, Any],
    meta: dict[str, Any],
    risk_facts: dict[str, Any],
    context: ProcessContext | None,
    strict: bool,
) -> tuple[Any, Any, str | None, str | None]:
    purchase = meta.get("purchase_order") if isinstance(meta.get("purchase_order"), dict) else {}
    ctx_purchase = context.purchase if context is not None else None

    amount = (
        params.get("amount")
        or meta.get("amount")
        or meta.get("required_amount")
        or meta.get("budget_amount")
        or purchase.get("amount")
        or (ctx_purchase.amount if ctx_purchase is not None else None)
        or risk_facts.get("purchase_amount")
    )
    vendor = (
        params.get("vendor_id")
        or meta.get("vendor_id")
        or meta.get("vendor")
        or purchase.get("vendor")
        or purchase.get("vendor_id")
        or (ctx_purchase.vendor_id if ctx_purchase is not None else None)
        or risk_facts.get("vendor_id")
    )
    currency = (
        params.get("currency")
        or meta.get("currency")
        or purchase.get("currency")
        or (ctx_purchase.currency if ctx_purchase is not None else None)
        or risk_facts.get("currency")
    )
    cost_centre = (
        params.get("cost_centre")
        or meta.get("cost_centre")
        or purchase.get("cost_centre")
        or (ctx_purchase.cost_centre if ctx_purchase is not None else None)
        or risk_facts.get("cost_centre")
    )

    if strict:
        missing = [
            field
            for field, value in (
                ("purchase.amount", amount),
                ("purchase.vendor_id", vendor),
                ("purchase.currency", currency),
            )
            if value in (None, "")
        ]
        if missing:
            raise MissingRequiredContextError(missing[0], missing_fields=missing)

    return vendor, amount, currency, cost_centre


def enrich_execute_parameters(
    *,
    process_id: str | None,
    process_type: str | None,
    process_name: str | None,
    metadata_json: dict[str, Any] | None,
    parameters: dict[str, Any] | None,
    strict: bool = False,
) -> dict[str, Any]:
    """Ensure Agent 2 gets tool parameters from ProcessContext / discovery.

    Never fills amount, currency, vendor, or cost centre with invented values.
    """
    params = dict(parameters or {})
    explicit_tool = (params.get("tool_name") or "").strip().lower()

    if explicit_tool and explicit_tool not in _LEGACY_SUITE_ALIASES and explicit_tool != FULL_TASK_SUITE_TOOL:
        if process_id:
            params.setdefault("process_id", process_id)
        if strict:
            _validate_required(params, metadata_json, process_type)
        return params

    if not _is_procurement(process_type):
        tool = _normalize_workflow_tool_name(params.get("tool_name"))
        if tool:
            params["tool_name"] = tool
        else:
            params.pop("tool_name", None)
        if process_id:
            params.setdefault("process_id", process_id)
        return params

    meta = metadata_json or {}
    risk_facts = _extract_risk_facts(meta)
    context = _context_from_meta(meta)
    try:
        vendor, amount, currency, cost_centre = _resolve_procurement_fields(
            params=params,
            meta=meta,
            risk_facts=risk_facts,
            context=context,
            strict=strict,
        )
    except MissingRequiredContextError:
        if strict:
            raise
        if process_id:
            params.setdefault("process_id", process_id)
        params.pop("tool_name", None)
        return params

    if amount is None or vendor is None or currency is None:
        if strict:
            missing = [
                name
                for name, value in (
                    ("purchase.amount", amount),
                    ("purchase.vendor_id", vendor),
                    ("purchase.currency", currency),
                )
                if value in (None, "")
            ]
            raise MissingRequiredContextError(missing[0] if missing else "purchase.amount", missing_fields=missing)
        if process_id:
            params.setdefault("process_id", process_id)
        params.pop("tool_name", None)
        return params

    try:
        amount_f = float(amount)
    except (TypeError, ValueError) as exc:
        if strict:
            raise MissingRequiredContextError("purchase.amount") from exc
        if process_id:
            params.setdefault("process_id", process_id)
        params.pop("tool_name", None)
        return params

    tool = _normalize_workflow_tool_name(params.get("tool_name"))
    if tool:
        params["tool_name"] = tool
    else:
        params.pop("tool_name", None)
    params.setdefault("vendor_id", str(vendor))
    params.setdefault("amount", amount_f)
    params.setdefault("currency", str(currency))
    if cost_centre not in (None, ""):
        params.setdefault("cost_centre", str(cost_centre))
    params.setdefault(
        "items_summary",
        f"{(process_name or 'Procurement')} line items",
    )
    if process_id:
        params.setdefault("process_id", process_id)
        params.setdefault("process_context_ref", process_id)
    return params


def require_enrich_execute_parameters(
    *,
    process_id: str | None,
    process_type: str | None,
    process_name: str | None,
    metadata_json: dict[str, Any] | None,
    parameters: dict[str, Any] | None,
) -> dict[str, Any]:
    """Strict enrichment for workflow autopilot and post-approval Agent 2 dispatch."""
    try:
        return enrich_execute_parameters(
            process_id=process_id,
            process_type=process_type,
            process_name=process_name,
            metadata_json=metadata_json,
            parameters=parameters,
            strict=True,
        )
    except MissingRequiredContextError as exc:
        raise ExecutionEnrichmentError(list(exc.missing_fields)) from exc


def _validate_required(
    params: dict[str, Any],
    metadata_json: dict[str, Any] | None,
    process_type: str | None,
) -> None:
    if not _is_procurement(process_type):
        return
    risk_facts = _extract_risk_facts(metadata_json)
    context = _context_from_meta(metadata_json)
    ctx_purchase = context.purchase if context is not None else None
    checks = {
        "purchase.vendor_id": params.get("vendor_id")
        or (ctx_purchase.vendor_id if ctx_purchase else None)
        or risk_facts.get("vendor_id"),
        "purchase.amount": params.get("amount")
        or (ctx_purchase.amount if ctx_purchase else None)
        or risk_facts.get("purchase_amount"),
        "purchase.currency": params.get("currency")
        or (ctx_purchase.currency if ctx_purchase else None)
        or risk_facts.get("currency"),
    }
    missing = [key for key, value in checks.items() if value in (None, "")]
    if missing:
        raise MissingRequiredContextError(missing[0], missing_fields=missing)
