"""Supabase REST read-path for Agent 3 when direct Postgres is unreachable."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.supabase_rest import rest_select

from ..interfaces import ResourceRepository
from ..schemas import BudgetResourceEvidence, HumanResourceEvidence


def _parse_dt(value: Any, *, default: Optional[datetime] = None) -> datetime:
    if value is None:
        if default is not None:
            return default
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class RestResourceRepository(ResourceRepository):
    """Load Agent 3 evidence from PostgREST (real seeded rows, not fixtures)."""

    async def get_human_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[HumanResourceEvidence]:
        tenant = str(tenant_id)
        resources = rest_select(
            "resources",
            {
                "select": "id,tenant_id,name,is_active,skills,availability_percentage",
                "tenant_id": f"eq.{tenant}",
                "type": "eq.HUMAN",
                "order": "id.asc",
            },
        )
        if not resources:
            return []

        roles = rest_select(
            "resource_roles",
            {"select": "resource_id,role_id", "tenant_id": f"eq.{tenant}"},
        )
        skills = rest_select(
            "resource_skills",
            {"select": "resource_id,skill_id", "tenant_id": f"eq.{tenant}"},
        )
        authorities = rest_select(
            "resource_authorities",
            {"select": "resource_id,authority_id", "tenant_id": f"eq.{tenant}"},
        )
        role_codes = {
            str(r["id"]): r["code"]
            for r in rest_select("roles", {"select": "id,code", "tenant_id": f"eq.{tenant}"})
        }
        skill_codes = {
            str(r["id"]): r["code"]
            for r in rest_select("skills", {"select": "id,code", "tenant_id": f"eq.{tenant}"})
        }
        authority_codes = {
            str(r["id"]): r["code"]
            for r in rest_select(
                "authorities", {"select": "id,code", "tenant_id": f"eq.{tenant}"}
            )
        }
        profiles = {
            str(r["resource_id"]): r
            for r in rest_select(
                "human_resource_profiles",
                {
                    "select": "resource_id,max_workload_pct,evidence_checked_at,evidence_valid_until",
                    "tenant_id": f"eq.{tenant}",
                },
            )
        }
        availability = {
            str(r["resource_id"]): r
            for r in rest_select(
                "resource_availability",
                {
                    "select": "resource_id,available_from,available_until",
                    "tenant_id": f"eq.{tenant}",
                },
            )
        }
        workloads = {
            str(r["resource_id"]): r
            for r in rest_select(
                "workload_snapshots",
                {
                    "select": "resource_id,current_workload_pct,max_workload_pct,snapshot_at",
                    "tenant_id": f"eq.{tenant}",
                    "order": "snapshot_at.desc",
                },
            )
        }

        roles_by_resource: Dict[str, List[str]] = {}
        for row in roles:
            rid = str(row["resource_id"])
            code = role_codes.get(str(row["role_id"]))
            if code:
                roles_by_resource.setdefault(rid, []).append(code)

        skills_by_resource: Dict[str, List[str]] = {}
        for row in skills:
            rid = str(row["resource_id"])
            code = skill_codes.get(str(row["skill_id"]))
            if code:
                skills_by_resource.setdefault(rid, []).append(code)

        authority_by_resource: Dict[str, Optional[str]] = {}
        for row in authorities:
            rid = str(row["resource_id"])
            authority_by_resource[rid] = authority_codes.get(str(row["authority_id"]))

        now = evaluation_timestamp if evaluation_timestamp.tzinfo else evaluation_timestamp.replace(
            tzinfo=timezone.utc
        )
        results: List[HumanResourceEvidence] = []
        for resource in resources:
            rid = str(resource["id"])
            profile = profiles.get(rid)
            avail = availability.get(rid)
            workload = workloads.get(rid)
            if profile is None:
                continue
            available_from = _parse_dt(
                (avail or {}).get("available_from"),
                default=now - timedelta(days=1),
            )
            available_until = None
            if avail and avail.get("available_until"):
                available_until = _parse_dt(avail["available_until"])
            if available_from > now:
                continue
            if available_until is not None and available_until < now:
                continue

            current = Decimal(str((workload or {}).get("current_workload_pct") or 0))
            max_wl = Decimal(
                str(
                    (workload or {}).get("max_workload_pct")
                    or profile.get("max_workload_pct")
                    or 100
                )
            )
            checked = _parse_dt(profile.get("evidence_checked_at"), default=now)
            valid_until = _parse_dt(
                profile.get("evidence_valid_until"),
                default=now + timedelta(days=30),
            )
            array_skills = resource.get("skills") or []
            mapped_skills = skills_by_resource.get(rid) or [
                str(s) for s in array_skills if s
            ]
            results.append(
                HumanResourceEvidence(
                    resource_id=_as_uuid(resource["id"]),
                    tenant_id=tenant_id,
                    name=str(resource["name"]),
                    is_active=bool(resource.get("is_active", True)),
                    roles=sorted(set(roles_by_resource.get(rid, []))),
                    mandatory_skills=sorted(set(mapped_skills)),
                    preferred_skills=[],
                    authority=authority_by_resource.get(rid),
                    available_from=available_from,
                    available_until=available_until,
                    current_workload_percentage=current,
                    max_workload_percentage=max_wl,
                    projected_workload_percentage=current,
                    segregation_of_duties_conflicts=[],
                    conflict_of_interest_flags=[],
                    evidence_checked_at=checked,
                    evidence_valid_until=valid_until,
                    evidence_references={"source": "supabase_rest"},
                )
            )
        return results

    async def get_budget_resources_by_tenant(
        self,
        tenant_id: UUID,
        evaluation_timestamp: datetime,
    ) -> List[BudgetResourceEvidence]:
        tenant = str(tenant_id)
        resources = rest_select(
            "resources",
            {
                "select": "id,tenant_id,name,is_active",
                "tenant_id": f"eq.{tenant}",
                "type": "eq.BUDGET",
                "order": "id.asc",
            },
        )
        profiles = {
            str(r["resource_id"]): r
            for r in rest_select(
                "budget_resource_profiles",
                {
                    "select": (
                        "resource_id,cost_centre,currency,available_balance,"
                        "authorization_limit,valid_from,valid_until,"
                        "evidence_checked_at,evidence_valid_until"
                    ),
                    "tenant_id": f"eq.{tenant}",
                },
            )
        }
        now = evaluation_timestamp if evaluation_timestamp.tzinfo else evaluation_timestamp.replace(
            tzinfo=timezone.utc
        )
        results: List[BudgetResourceEvidence] = []
        for resource in resources:
            if not resource.get("is_active", True):
                continue
            rid = str(resource["id"])
            profile = profiles.get(rid)
            if profile is None:
                continue
            valid_from = _parse_dt(profile.get("valid_from"), default=now - timedelta(days=1))
            valid_until = (
                _parse_dt(profile["valid_until"]) if profile.get("valid_until") else None
            )
            if valid_from > now:
                continue
            if valid_until is not None and valid_until < now:
                continue
            checked = _parse_dt(profile.get("evidence_checked_at"), default=now)
            evidence_valid = _parse_dt(
                profile.get("evidence_valid_until"),
                default=now + timedelta(days=30),
            )
            auth_limit = profile.get("authorization_limit")
            results.append(
                BudgetResourceEvidence(
                    resource_id=_as_uuid(resource["id"]),
                    tenant_id=tenant_id,
                    name=str(resource["name"]),
                    available_balance=Decimal(str(profile.get("available_balance") or 0)),
                    currency=str(profile.get("currency") or "USD"),
                    cost_centre=profile.get("cost_centre"),
                    valid_from=valid_from,
                    valid_until=valid_until,
                    authorization_limit=(
                        Decimal(str(auth_limit)) if auth_limit is not None else None
                    ),
                    evidence_checked_at=checked,
                    evidence_valid_until=evidence_valid,
                    evidence_references={"source": "supabase_rest"},
                )
            )
        return results
