"""Approval request persistence for Agent 4.

In-memory for unit tests; SQLAlchemy async for PostgreSQL.
When the Postgres pooler is unreachable, list/get fall back to Supabase REST.
"""

from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.supabase_rest import (
    rest_insert,
    rest_select,
    rest_update,
    supabase_rest_configured,
    use_supabase_rest_fallback,
)
from app.models.approval import ApprovalRequest
from app.models.audit import AuditLog

from .constants import ApprovalStatus, RiskLevel
from .exceptions import (
    ApprovalAlreadyDecidedError,
    ApprovalNotFoundError,
    DatabasePersistenceError,
)
from .repository import AUDIT_ACTION_UPDATED, AUDIT_ENTITY_PROCESS
from .schemas import ApprovalRequestRecord

AUDIT_ACTION_CREATED = "created"
AUDIT_ACTION_COMPLETED = "completed"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def approval_from_orm(row: ApprovalRequest) -> ApprovalRequestRecord:
    decision = None
    if row.decision is not None:
        decision = ApprovalStatus(row.decision)
    return ApprovalRequestRecord(
        id=row.id,
        process_id=row.process_id,
        task_id=row.task_id,
        requested_by=row.requested_by,
        approver_id=row.approver_id,
        status=ApprovalStatus(row.status),
        risk_level=RiskLevel(row.risk_level),
        reason=row.reason,
        decision=decision,
        comments=row.comments,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def approval_from_rest(row: dict) -> ApprovalRequestRecord:
    return ApprovalRequestRecord.model_validate(
        {
            "id": row["id"],
            "process_id": row["process_id"],
            "task_id": row.get("task_id"),
            "requested_by": row.get("requested_by"),
            "approver_id": row.get("approver_id"),
            "status": row["status"],
            "risk_level": row["risk_level"],
            "reason": row["reason"],
            "decision": row.get("decision"),
            "comments": row.get("comments"),
            "created_at": row["created_at"],
            "decided_at": row.get("decided_at"),
        }
    )


def _list_approvals_rest(status: ApprovalStatus | None) -> List[ApprovalRequestRecord]:
    params: dict[str, str] = {
        "select": "id,process_id,task_id,requested_by,approver_id,status,risk_level,reason,decision,comments,created_at,decided_at",
        "order": "created_at.desc",
    }
    if status is not None:
        params["status"] = f"eq.{status.value}"
    return [approval_from_rest(row) for row in rest_select("approval_requests", params)]


def _get_approval_rest(approval_id: UUID) -> ApprovalRequestRecord:
    rows = rest_select(
        "approval_requests",
        {
            "id": f"eq.{approval_id}",
            "select": "id,process_id,task_id,requested_by,approver_id,status,risk_level,reason,decision,comments,created_at,decided_at",
            "limit": "1",
        },
    )
    if not rows:
        raise ApprovalNotFoundError(approval_id)
    return approval_from_rest(rows[0])


def _create_approval_rest(
    process_id: UUID,
    risk_level: RiskLevel,
    reason: str,
    task_id: UUID | None,
    requested_by: UUID | None,
    approver_id: UUID | None,
) -> ApprovalRequestRecord:
    safe_task_id: UUID | None = None
    if task_id is not None:
        existing = rest_select(
            "tasks",
            {"id": f"eq.{task_id}", "select": "id", "limit": "1"},
        )
        if existing:
            safe_task_id = task_id
    row = rest_insert(
        "approval_requests",
        {
            "process_id": str(process_id),
            "task_id": str(safe_task_id) if safe_task_id else None,
            "requested_by": str(requested_by) if requested_by else None,
            "approver_id": str(approver_id) if approver_id else None,
            "status": ApprovalStatus.PENDING.value,
            "risk_level": risk_level.value,
            "reason": reason,
        },
    )
    rest_insert(
        "audit_logs",
        {
            "entity_type": AUDIT_ENTITY_PROCESS,
            "entity_id": str(process_id),
            "action": AUDIT_ACTION_CREATED,
            "performed_by": str(requested_by) if requested_by else None,
            "new_values": {
                "approval_request_id": row.get("id"),
                "status": ApprovalStatus.PENDING.value,
                "risk_level": risk_level.value,
                "reason": reason,
            },
        },
    )
    return approval_from_rest(row)


def _decide_approval_rest(
    approval_id: UUID,
    approver_id: UUID,
    decision: ApprovalStatus,
    comments: str | None,
) -> ApprovalRequestRecord:
    current = _get_approval_rest(approval_id)
    if current.status is not ApprovalStatus.PENDING:
        raise ApprovalAlreadyDecidedError(approval_id, current.status.value)
    decided_at = utc_now().isoformat()
    row = rest_update(
        "approval_requests",
        {"id": f"eq.{approval_id}"},
        {
            "status": decision.value,
            "decision": decision.value,
            "approver_id": str(approver_id),
            "comments": comments,
            "decided_at": decided_at,
        },
    )
    rest_insert(
        "audit_logs",
        {
            "entity_type": AUDIT_ENTITY_PROCESS,
            "entity_id": str(current.process_id),
            "action": AUDIT_ACTION_COMPLETED,
            "performed_by": str(approver_id),
            "old_values": {"status": ApprovalStatus.PENDING.value, "decision": None},
            "new_values": {
                "approval_request_id": str(approval_id),
                "status": decision.value,
                "decision": decision.value,
                "comments": comments,
            },
        },
    )
    if isinstance(row, dict) and row.get("id"):
        return approval_from_rest(row)
    return _get_approval_rest(approval_id)


class ApprovalRepository(ABC):
    """Persistence for human approval requests and related audit events."""

    @abstractmethod
    async def create_approval_request(
        self,
        process_id: UUID,
        risk_level: RiskLevel,
        reason: str,
        task_id: UUID | None = None,
        requested_by: UUID | None = None,
        approver_id: UUID | None = None,
    ) -> ApprovalRequestRecord:
        """Insert a PENDING approval request."""

    @abstractmethod
    async def get_approval_request(self, approval_id: UUID) -> ApprovalRequestRecord:
        """Load one approval request."""

    @abstractmethod
    async def get_pending_approval_for_process(
        self,
        process_id: UUID,
    ) -> ApprovalRequestRecord | None:
        """Return the pending approval for a process, if any."""

    @abstractmethod
    async def list_approval_requests(
        self,
        status: ApprovalStatus | None = None,
    ) -> List[ApprovalRequestRecord]:
        """Return approval requests, optionally filtered by status."""

    @abstractmethod
    async def approve_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalRequestRecord:
        """Mark a pending request APPROVED."""

    @abstractmethod
    async def reject_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalRequestRecord:
        """Mark a pending request REJECTED."""

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class InMemoryApprovalRepository(ApprovalRepository):
    """In-memory stand-in used by unit tests."""

    def __init__(self) -> None:
        self._records: Dict[UUID, ApprovalRequestRecord] = {}
        self.audit_events: List[dict] = []

    async def create_approval_request(
        self,
        process_id: UUID,
        risk_level: RiskLevel,
        reason: str,
        task_id: UUID | None = None,
        requested_by: UUID | None = None,
        approver_id: UUID | None = None,
    ) -> ApprovalRequestRecord:
        record = ApprovalRequestRecord(
            id=uuid4(),
            process_id=process_id,
            task_id=task_id,
            requested_by=requested_by,
            approver_id=approver_id,
            status=ApprovalStatus.PENDING,
            risk_level=risk_level,
            reason=reason,
            decision=None,
            comments=None,
            created_at=utc_now(),
            decided_at=None,
        )
        self._records[record.id] = record
        self.audit_events.append(
            {
                "entity_type": AUDIT_ENTITY_PROCESS,
                "entity_id": process_id,
                "action": AUDIT_ACTION_CREATED,
                "old_values": None,
                "new_values": {
                    "approval_request_id": str(record.id),
                    "status": ApprovalStatus.PENDING.value,
                    "risk_level": risk_level.value,
                    "reason": reason,
                },
            }
        )
        return record

    async def get_approval_request(self, approval_id: UUID) -> ApprovalRequestRecord:
        if approval_id not in self._records:
            raise ApprovalNotFoundError(approval_id)
        return self._records[approval_id]

    async def get_pending_approval_for_process(
        self,
        process_id: UUID,
    ) -> ApprovalRequestRecord | None:
        for record in self._records.values():
            if (
                record.process_id == process_id
                and record.status is ApprovalStatus.PENDING
            ):
                return record
        return None

    async def list_approval_requests(
        self,
        status: ApprovalStatus | None = None,
    ) -> List[ApprovalRequestRecord]:
        records = list(self._records.values())
        if status is not None:
            records = [record for record in records if record.status is status]
        records.sort(key=lambda record: record.created_at, reverse=True)
        return records

    async def approve_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalRequestRecord:
        return self._decide(
            approval_id,
            approver_id,
            ApprovalStatus.APPROVED,
            comments,
        )

    async def reject_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalRequestRecord:
        return self._decide(
            approval_id,
            approver_id,
            ApprovalStatus.REJECTED,
            comments,
        )

    def _decide(
        self,
        approval_id: UUID,
        approver_id: UUID,
        decision: ApprovalStatus,
        comments: str | None,
    ) -> ApprovalRequestRecord:
        current = self._records.get(approval_id)
        if current is None:
            raise ApprovalNotFoundError(approval_id)
        if current.status is not ApprovalStatus.PENDING:
            raise ApprovalAlreadyDecidedError(approval_id, current.status.value)
        updated = current.model_copy(
            update={
                "status": decision,
                "decision": decision,
                "approver_id": approver_id,
                "comments": comments,
                "decided_at": utc_now(),
            }
        )
        self._records[approval_id] = updated
        self.audit_events.append(
            {
                "entity_type": AUDIT_ENTITY_PROCESS,
                "entity_id": current.process_id,
                "action": AUDIT_ACTION_COMPLETED,
                "performed_by": str(approver_id),
                "old_values": {"status": ApprovalStatus.PENDING.value, "decision": None},
                "new_values": {
                    "approval_request_id": str(approval_id),
                    "status": decision.value,
                    "decision": decision.value,
                    "comments": comments,
                },
            }
        )
        return updated


class SqlAlchemyApprovalRepository(ApprovalRepository):
    """PostgreSQL persistence for approval_requests via async SQLAlchemy."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _prefer_rest(self) -> bool:
        return use_supabase_rest_fallback()

    async def create_approval_request(
        self,
        process_id: UUID,
        risk_level: RiskLevel,
        reason: str,
        task_id: UUID | None = None,
        requested_by: UUID | None = None,
        approver_id: UUID | None = None,
    ) -> ApprovalRequestRecord:
        if self._prefer_rest():
            return await asyncio.to_thread(
                _create_approval_rest,
                process_id,
                risk_level,
                reason,
                task_id,
                requested_by,
                approver_id,
            )
        created_at = utc_now()
        row = ApprovalRequest(
            id=uuid4(),
            process_id=process_id,
            task_id=task_id,
            requested_by=requested_by,
            approver_id=approver_id,
            status=ApprovalStatus.PENDING.value,
            risk_level=risk_level.value,
            reason=reason,
            decision=None,
            comments=None,
            created_at=created_at,
            decided_at=None,
        )
        try:
            self._session.add(row)
            self._session.add(
                AuditLog(
                    id=uuid4(),
                    entity_type=AUDIT_ENTITY_PROCESS,
                    entity_id=process_id,
                    action=AUDIT_ACTION_CREATED,
                    performed_by=requested_by,
                    old_values=None,
                    new_values={
                        "approval_request_id": str(row.id),
                        "status": ApprovalStatus.PENDING.value,
                        "risk_level": risk_level.value,
                        "reason": reason,
                    },
                    timestamp=created_at,
                )
            )
            await self._session.flush()
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(
                        _create_approval_rest,
                        process_id,
                        risk_level,
                        reason,
                        task_id,
                        requested_by,
                        approver_id,
                    )
                except Exception:
                    pass
            raise DatabasePersistenceError(
                f"Failed to create approval request for process {process_id}"
            ) from exc
        return approval_from_orm(row)

    async def get_approval_request(self, approval_id: UUID) -> ApprovalRequestRecord:
        if self._prefer_rest():
            return await asyncio.to_thread(_get_approval_rest, approval_id)
        try:
            row = await self._get_row(approval_id)
            return approval_from_orm(row)
        except Exception:
            if supabase_rest_configured():
                return await asyncio.to_thread(_get_approval_rest, approval_id)
            raise

    async def get_pending_approval_for_process(
        self,
        process_id: UUID,
    ) -> ApprovalRequestRecord | None:
        if self._prefer_rest():
            rows = await asyncio.to_thread(_list_approvals_rest, ApprovalStatus.PENDING)
            for row in rows:
                if row.process_id == process_id:
                    return row
            return None
        try:
            result = await self._session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.process_id == process_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING.value,
                )
            )
            row = result.scalars().first()
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    rows = await asyncio.to_thread(
                        _list_approvals_rest, ApprovalStatus.PENDING
                    )
                    for item in rows:
                        if item.process_id == process_id:
                            return item
                    return None
                except Exception:
                    pass
            raise DatabasePersistenceError(
                f"Failed to load pending approval for process {process_id}"
            ) from exc
        if row is None:
            return None
        return approval_from_orm(row)

    async def list_approval_requests(
        self,
        status: ApprovalStatus | None = None,
    ) -> List[ApprovalRequestRecord]:
        if self._prefer_rest():
            return await asyncio.to_thread(_list_approvals_rest, status)
        try:
            stmt = select(ApprovalRequest).order_by(ApprovalRequest.created_at.desc())
            if status is not None:
                stmt = stmt.where(ApprovalRequest.status == status.value)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(_list_approvals_rest, status)
                except Exception:
                    pass
            raise DatabasePersistenceError("Failed to list approval requests") from exc
        return [approval_from_orm(row) for row in rows]

    async def approve_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalRequestRecord:
        return await self._decide(
            approval_id,
            approver_id,
            ApprovalStatus.APPROVED,
            comments,
        )

    async def reject_request(
        self,
        approval_id: UUID,
        approver_id: UUID,
        comments: str | None = None,
    ) -> ApprovalRequestRecord:
        return await self._decide(
            approval_id,
            approver_id,
            ApprovalStatus.REJECTED,
            comments,
        )

    async def commit(self) -> None:
        if self._prefer_rest():
            return
        try:
            await self._session.commit()
        except Exception as exc:
            await self._session.rollback()
            raise DatabasePersistenceError(
                "Failed to commit approval request change"
            ) from exc

    async def rollback(self) -> None:
        if self._prefer_rest():
            return
        try:
            await self._session.rollback()
        except Exception as exc:
            raise DatabasePersistenceError(
                "Failed to roll back approval request change"
            ) from exc

    async def _decide(
        self,
        approval_id: UUID,
        approver_id: UUID,
        decision: ApprovalStatus,
        comments: str | None,
    ) -> ApprovalRequestRecord:
        if self._prefer_rest():
            return await asyncio.to_thread(
                _decide_approval_rest,
                approval_id,
                approver_id,
                decision,
                comments,
            )
        row = await self._get_row(approval_id)
        if row.status != ApprovalStatus.PENDING.value:
            raise ApprovalAlreadyDecidedError(approval_id, row.status)
        decided_at = utc_now()
        old_status = row.status
        try:
            row.status = decision.value
            row.decision = decision.value
            row.approver_id = approver_id
            row.comments = comments
            row.decided_at = decided_at
            self._session.add(
                AuditLog(
                    id=uuid4(),
                    entity_type=AUDIT_ENTITY_PROCESS,
                    entity_id=row.process_id,
                    action=AUDIT_ACTION_COMPLETED,
                    performed_by=approver_id,
                    old_values={"status": old_status, "decision": None},
                    new_values={
                        "approval_request_id": str(approval_id),
                        "status": decision.value,
                        "decision": decision.value,
                        "comments": comments,
                    },
                    timestamp=decided_at,
                )
            )
            await self._session.flush()
        except (ApprovalAlreadyDecidedError, ApprovalNotFoundError):
            raise
        except Exception as exc:
            if supabase_rest_configured():
                try:
                    return await asyncio.to_thread(
                        _decide_approval_rest,
                        approval_id,
                        approver_id,
                        decision,
                        comments,
                    )
                except Exception:
                    pass
            raise DatabasePersistenceError(
                f"Failed to record approval decision {approval_id}"
            ) from exc
        return approval_from_orm(row)

    async def _get_row(self, approval_id: UUID) -> ApprovalRequest:
        try:
            row = await self._session.get(ApprovalRequest, approval_id)
        except Exception as exc:
            raise DatabasePersistenceError(
                f"Failed to load approval request {approval_id}"
            ) from exc
        if row is None:
            raise ApprovalNotFoundError(approval_id)
        return row
