"""Build Agent 2 execution payloads from process metadata.

Shared by POST /processes/{id}/execute, process autopilot (Agent 4), and the
post-approval dispatch path. Workflow execution always runs the full Agent 2
tool suite (__full_task_suite__) with parameters derived from Agent 1 discovery.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.agent2_execution.agent.planner_fallback import FULL_TASK_SUITE_TOOL

from .exceptions import ExecutionEnrichmentError

_PROCUREMENT_TYPES = frozenset(
    {"PROCUREMENT", "PURCHASE", "PO", "PURCHASE_ORDER", "BUY"}
)

_REQUIRED_PROCUREMENT_FIELDS = ("vendor_id", "amount", "currency", "cost_centre")

_DEFAULT_CURRENCY = "USD"
_DEFAULT_COST_CENTRE = "IT-OPS"
_DEFAULT_VENDOR_ID = "VENDOR-ACME"
_DEFAULT_AMOUNT = 2500.0

# Legacy single-tool dispatch names upgraded to the workflow suite automatically.
_LEGACY_SUITE_ALIASES = frozenset({"create_po_draft", "execute_task", "execute_po_draft"})


def build_process_execution_metadata(process: Any) -> dict[str, Any]:
    """Merge metadata_json and process_json for enrichment (Agent 1 discovery output)."""
    meta = dict(getattr(process, "metadata_json", None) or {})
    process_json = getattr(process, "process_json", None)
    if isinstance(process_json, dict):
        meta = meta | {"process_json": process_json}
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


def _is_procurement(process_type: str | None) -> bool:
    process_type_u = (process_type or "PROCUREMENT").upper()
    if process_type_u in _PROCUREMENT_TYPES or process_type_u.endswith("PROCUREMENT"):
        return True
    return process_type_u in {"GENERAL", "GENERIC", ""}


def _vendor_from_name(name: str | None) -> str | None:
    if not name or not str(name).strip():
        return None
    slug = re.sub(r"[^A-Z0-9]+", "-", str(name).upper()).strip("-")
    return f"VENDOR-{slug[:32]}" if slug else None


def _normalize_workflow_tool_name(tool_name: str | None) -> str | None:
    """Map workflow dispatch to the full Agent 2 suite unless a specific tool was requested."""
    clean = (tool_name or "").strip().lower()
    if not clean or clean in _LEGACY_SUITE_ALIASES or clean == FULL_TASK_SUITE_TOOL:
        return FULL_TASK_SUITE_TOOL
    return clean


def _resolve_procurement_fields(
    *,
    params: dict[str, Any],
    meta: dict[str, Any],
    risk_facts: dict[str, Any],
    strict: bool,
) -> tuple[Any, Any, str, str]:
    purchase = meta.get("purchase_order") if isinstance(meta.get("purchase_order"), dict) else {}

    amount = (
        params.get("amount")
        or meta.get("amount")
        or meta.get("required_amount")
        or meta.get("budget_amount")
        or purchase.get("amount")
        or risk_facts.get("purchase_amount")
    )
    vendor = (
        params.get("vendor_id")
        or meta.get("vendor_id")
        or meta.get("vendor")
        or purchase.get("vendor")
        or purchase.get("vendor_id")
        or risk_facts.get("vendor_id")
        or _vendor_from_name(risk_facts.get("vendor_name"))
    )
    currency = (
        params.get("currency")
        or meta.get("currency")
        or purchase.get("currency")
        or risk_facts.get("currency")
        or _DEFAULT_CURRENCY
    )
    cost_centre = (
        params.get("cost_centre")
        or meta.get("cost_centre")
        or purchase.get("cost_centre")
        or risk_facts.get("cost_centre")
        or _DEFAULT_COST_CENTRE
    )

    if vendor in (None, "") and strict:
        vendor = _DEFAULT_VENDOR_ID
    if amount in (None, "") and strict:
        amount = _DEFAULT_AMOUNT

    if strict:
        missing = [
            field
            for field, value in (
                ("vendor_id", vendor),
                ("amount", amount),
                ("currency", currency),
                ("cost_centre", cost_centre),
            )
            if value in (None, "")
        ]
        if missing:
            raise ExecutionEnrichmentError(missing)

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
    """Ensure Agent 2 gets actionable tool parameters from discovery metadata."""
    params = dict(parameters or {})
    explicit_tool = (params.get("tool_name") or "").strip().lower()

    # Operator invoked a specific tool manually (Tools page / API) — honour it.
    if explicit_tool and explicit_tool not in _LEGACY_SUITE_ALIASES and explicit_tool != FULL_TASK_SUITE_TOOL:
        if process_id:
            params.setdefault("process_id", process_id)
        if strict:
            _validate_required(params, metadata_json, process_type)
        return params

    if not _is_procurement(process_type):
        params["tool_name"] = _normalize_workflow_tool_name(params.get("tool_name")) or FULL_TASK_SUITE_TOOL
        if process_id:
            params.setdefault("process_id", process_id)
        return params

    meta = metadata_json or {}
    risk_facts = _extract_risk_facts(meta)
    vendor, amount, currency, cost_centre = _resolve_procurement_fields(
        params=params,
        meta=meta,
        risk_facts=risk_facts,
        strict=strict,
    )

    if amount is None or vendor is None:
        if strict:
            raise ExecutionEnrichmentError(list(_REQUIRED_PROCUREMENT_FIELDS))
        params["tool_name"] = FULL_TASK_SUITE_TOOL
        if process_id:
            params.setdefault("process_id", process_id)
        return params

    try:
        amount_f = float(amount)
    except (TypeError, ValueError) as exc:
        if strict:
            raise ExecutionEnrichmentError(["amount"]) from exc
        params["tool_name"] = FULL_TASK_SUITE_TOOL
        if process_id:
            params.setdefault("process_id", process_id)
        return params

    params["tool_name"] = FULL_TASK_SUITE_TOOL
    params.setdefault("vendor_id", str(vendor))
    params.setdefault("amount", amount_f)
    params.setdefault("currency", str(currency))
    params.setdefault("cost_centre", str(cost_centre))
    params.setdefault(
        "items_summary",
        f"{(process_name or 'Procurement')} line items",
    )
    if process_id:
        params.setdefault("process_id", process_id)
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
    return enrich_execute_parameters(
        process_id=process_id,
        process_type=process_type,
        process_name=process_name,
        metadata_json=metadata_json,
        parameters=parameters,
        strict=True,
    )


def _validate_required(
    params: dict[str, Any],
    metadata_json: dict[str, Any] | None,
    process_type: str | None,
) -> None:
    if not _is_procurement(process_type):
        return
    risk_facts = _extract_risk_facts(metadata_json)
    checks = {
        "vendor_id": params.get("vendor_id") or risk_facts.get("vendor_id"),
        "amount": params.get("amount") or risk_facts.get("purchase_amount"),
        "currency": params.get("currency") or risk_facts.get("currency") or _DEFAULT_CURRENCY,
        "cost_centre": params.get("cost_centre") or risk_facts.get("cost_centre") or _DEFAULT_COST_CENTRE,
    }
    missing = [key for key, value in checks.items() if value in (None, "")]
    if missing:
        raise ExecutionEnrichmentError(missing)
