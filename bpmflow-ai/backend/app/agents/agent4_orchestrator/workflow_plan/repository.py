"""WorkflowPlan persistence: in-memory tests + SQLAlchemy production path."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.process import Process
from app.models.workflow import WorkflowPlan, WorkflowStep, WorkflowStepDependency

from .constants import CREATED_BY_AGENT4, WorkflowPlanStatus, WorkflowStepStatus, WorkflowStepType
from .exceptions import (
    DuplicateDependencyError,
    DuplicateStepKeyError,
    WorkflowPlanNotFoundError,
    WorkflowStepNotFoundError,
)
from .schemas import (
    CreateWorkflowStepInput,
    WorkflowEvidenceRef,
    WorkflowPlanRecord,
    WorkflowPolicyRef,
    WorkflowStepRecord,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProcessBindingRecord:
    def __init__(
        self,
        *,
        id: UUID,
        tenant_id: UUID | None,
        process_context_schema_version: str | None = None,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.process_context_schema_version = process_context_schema_version


class WorkflowPlanRepository(ABC):
    @abstractmethod
    async def get_process_binding(self, process_id: UUID) -> ProcessBindingRecord | None: ...

    @abstractmethod
    async def register_process(
        self,
        process_id: UUID,
        tenant_id: UUID,
        *,
        process_context_schema_version: str | None = None,
    ) -> ProcessBindingRecord: ...

    @abstractmethod
    async def insert_plan(self, plan: WorkflowPlanRecord) -> WorkflowPlanRecord: ...

    @abstractmethod
    async def get_plan(
        self, workflow_plan_id: UUID, *, tenant_id: UUID | None = None
    ) -> WorkflowPlanRecord: ...

    @abstractmethod
    async def list_plans_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[WorkflowPlanRecord]: ...

    @abstractmethod
    async def get_active_plan(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> WorkflowPlanRecord | None: ...

    @abstractmethod
    async def get_plan_version(
        self, *, tenant_id: UUID, process_id: UUID, version: int
    ) -> WorkflowPlanRecord | None: ...

    @abstractmethod
    async def update_plan_status(
        self, workflow_plan_id: UUID, status: WorkflowPlanStatus, *, tenant_id: UUID
    ) -> WorkflowPlanRecord: ...

    @abstractmethod
    async def add_step(
        self, workflow_plan_id: UUID, payload: CreateWorkflowStepInput, *, tenant_id: UUID
    ) -> WorkflowStepRecord: ...

    @abstractmethod
    async def replace_step(
        self, workflow_plan_id: UUID, payload: CreateWorkflowStepInput, *, tenant_id: UUID
    ) -> WorkflowStepRecord: ...

    @abstractmethod
    async def add_dependency(
        self,
        *,
        tenant_id: UUID,
        workflow_plan_id: UUID,
        step_key: str,
        depends_on_step_key: str,
    ) -> None: ...

    @abstractmethod
    async def list_steps(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> list[WorkflowStepRecord]: ...

    @abstractmethod
    async def update_step_status(
        self,
        workflow_plan_id: UUID,
        workflow_step_id: UUID,
        status: WorkflowStepStatus,
        *,
        tenant_id: UUID,
    ) -> WorkflowStepRecord: ...

    @abstractmethod
    async def claim_step_execution(
        self, workflow_plan_id: UUID, workflow_step_id: UUID, *, tenant_id: UUID
    ) -> bool: ...


class InMemoryWorkflowPlanRepository(WorkflowPlanRepository):
    def __init__(self) -> None:
        self._plans: dict[UUID, WorkflowPlanRecord] = {}
        self._processes: dict[UUID, ProcessBindingRecord] = {}
        self._step_locks: dict[UUID, asyncio.Lock] = {}

    async def get_process_binding(self, process_id: UUID) -> ProcessBindingRecord | None:
        return self._processes.get(process_id)

    async def register_process(
        self,
        process_id: UUID,
        tenant_id: UUID,
        *,
        process_context_schema_version: str | None = None,
    ) -> ProcessBindingRecord:
        record = ProcessBindingRecord(
            id=process_id,
            tenant_id=tenant_id,
            process_context_schema_version=process_context_schema_version,
        )
        self._processes[process_id] = record
        return record

    async def insert_plan(self, plan: WorkflowPlanRecord) -> WorkflowPlanRecord:
        stored = deepcopy(plan)
        stored.created_at = stored.created_at or _utc_now()
        stored.updated_at = stored.updated_at or stored.created_at
        self._plans[stored.id] = stored
        return deepcopy(stored)

    async def get_plan(
        self, workflow_plan_id: UUID, *, tenant_id: UUID | None = None
    ) -> WorkflowPlanRecord:
        plan = self._plans.get(workflow_plan_id)
        if plan is None or (tenant_id is not None and plan.tenant_id != tenant_id):
            raise WorkflowPlanNotFoundError(workflow_plan_id)
        return deepcopy(plan)

    async def list_plans_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[WorkflowPlanRecord]:
        plans = [
            deepcopy(plan)
            for plan in self._plans.values()
            if plan.tenant_id == tenant_id and plan.process_id == process_id
        ]
        return sorted(plans, key=lambda item: item.version)

    async def get_active_plan(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> WorkflowPlanRecord | None:
        for plan in self._plans.values():
            if (
                plan.tenant_id == tenant_id
                and plan.process_id == process_id
                and plan.status == WorkflowPlanStatus.ACTIVE
            ):
                return deepcopy(plan)
        return None

    async def get_plan_version(
        self, *, tenant_id: UUID, process_id: UUID, version: int
    ) -> WorkflowPlanRecord | None:
        for plan in self._plans.values():
            if (
                plan.tenant_id == tenant_id
                and plan.process_id == process_id
                and plan.version == version
            ):
                return deepcopy(plan)
        return None

    async def update_plan_status(
        self, workflow_plan_id: UUID, status: WorkflowPlanStatus, *, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        plan.status = status
        plan.updated_at = _utc_now()
        if status == WorkflowPlanStatus.ACTIVE:
            for step in plan.steps:
                if step.status != WorkflowStepStatus.PENDING:
                    continue
                step.status = (
                    WorkflowStepStatus.WAITING_DEPENDENCY
                    if step.depends_on_step_keys
                    else WorkflowStepStatus.READY
                )
        self._plans[plan.id] = deepcopy(plan)
        return deepcopy(plan)

    async def add_step(
        self, workflow_plan_id: UUID, payload: CreateWorkflowStepInput, *, tenant_id: UUID
    ) -> WorkflowStepRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        if any(step.step_key == payload.step_key for step in plan.steps):
            raise DuplicateStepKeyError(f"Duplicate step_key '{payload.step_key}'")
        if any(step.sequence == payload.sequence for step in plan.steps):
            raise DuplicateStepKeyError(f"Duplicate sequence {payload.sequence}")
        existing_keys = {step.step_key for step in plan.steps}
        for dep in payload.depends_on_step_keys:
            if dep not in existing_keys and dep != payload.step_key:
                # Allow forward refs only if the dependency already exists.
                raise WorkflowStepNotFoundError(dep)
        step = _step_from_input(plan, payload)
        plan.steps.append(step)
        plan.steps.sort(key=lambda item: item.sequence)
        plan.updated_at = _utc_now()
        self._plans[plan.id] = deepcopy(plan)
        return deepcopy(step)

    async def replace_step(
        self, workflow_plan_id: UUID, payload: CreateWorkflowStepInput, *, tenant_id: UUID
    ) -> WorkflowStepRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        index = next(
            (i for i, step in enumerate(plan.steps) if step.step_key == payload.step_key),
            None,
        )
        if index is None:
            raise WorkflowStepNotFoundError(payload.step_key)
        existing = plan.steps[index]
        if any(
            step.sequence == payload.sequence and step.step_key != payload.step_key
            for step in plan.steps
        ):
            raise DuplicateStepKeyError(f"Duplicate sequence {payload.sequence}")
        step = _step_from_input(plan, payload, step_id=existing.id, created_at=existing.created_at)
        plan.steps[index] = step
        plan.steps.sort(key=lambda item: item.sequence)
        plan.updated_at = _utc_now()
        self._plans[plan.id] = deepcopy(plan)
        return deepcopy(step)

    async def add_dependency(
        self,
        *,
        tenant_id: UUID,
        workflow_plan_id: UUID,
        step_key: str,
        depends_on_step_key: str,
    ) -> None:
        if step_key == depends_on_step_key:
            raise DuplicateDependencyError("A step cannot depend on itself")
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        keys = {step.step_key: step for step in plan.steps}
        if step_key not in keys:
            raise WorkflowStepNotFoundError(step_key)
        if depends_on_step_key not in keys:
            raise WorkflowStepNotFoundError(depends_on_step_key)
        step = keys[step_key]
        if depends_on_step_key in step.depends_on_step_keys:
            raise DuplicateDependencyError(
                f"Duplicate dependency {step_key} -> {depends_on_step_key}"
            )
        step.depends_on_step_keys.append(depends_on_step_key)
        plan.updated_at = _utc_now()
        self._plans[plan.id] = deepcopy(plan)

    async def list_steps(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> list[WorkflowStepRecord]:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        return sorted(deepcopy(plan.steps), key=lambda item: item.sequence)

    def _step_index(self, plan: WorkflowPlanRecord, workflow_step_id: UUID) -> int:
        index = next((i for i, step in enumerate(plan.steps) if step.id == workflow_step_id), None)
        if index is None:
            raise WorkflowStepNotFoundError(str(workflow_step_id))
        return index

    async def update_step_status(
        self,
        workflow_plan_id: UUID,
        workflow_step_id: UUID,
        status: WorkflowStepStatus,
        *,
        tenant_id: UUID,
    ) -> WorkflowStepRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        index = self._step_index(plan, workflow_step_id)
        plan.steps[index].status = status
        plan.steps[index].updated_at = _utc_now()
        plan.updated_at = _utc_now()
        self._plans[plan.id] = deepcopy(plan)
        return deepcopy(plan.steps[index])

    async def claim_step_execution(
        self, workflow_plan_id: UUID, workflow_step_id: UUID, *, tenant_id: UUID
    ) -> bool:
        lock = self._step_locks.setdefault(workflow_step_id, asyncio.Lock())
        async with lock:
            plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
            index = self._step_index(plan, workflow_step_id)
            current = plan.steps[index].status
            if current is WorkflowStepStatus.IN_PROGRESS:
                return False
            if current is WorkflowStepStatus.COMPLETED:
                return False
            if current not in {
                WorkflowStepStatus.READY,
                WorkflowStepStatus.AUTHORIZED,
                WorkflowStepStatus.WAITING_DEPENDENCY,
                WorkflowStepStatus.PENDING,
            }:
                return False
            plan.steps[index].status = WorkflowStepStatus.IN_PROGRESS
            plan.steps[index].updated_at = _utc_now()
            self._plans[plan.id] = deepcopy(plan)
            return True


def _step_from_input(
    plan: WorkflowPlanRecord,
    payload: CreateWorkflowStepInput,
    *,
    step_id: UUID | None = None,
    created_at: datetime | None = None,
) -> WorkflowStepRecord:
    now = _utc_now()
    return WorkflowStepRecord(
        id=step_id or uuid4(),
        tenant_id=plan.tenant_id,
        workflow_plan_id=plan.id,
        step_key=payload.step_key,
        sequence=payload.sequence,
        name=payload.name,
        description=payload.description,
        step_type=payload.step_type,
        status=payload.status,
        responsible_employee_id=payload.responsible_employee_id,
        responsible_resource_id=payload.responsible_resource_id,
        responsible_role_id=payload.responsible_role_id,
        responsible_department_id=payload.responsible_department_id,
        assignment_unresolved=payload.assignment_unresolved,
        unresolved_reason=payload.unresolved_reason,
        depends_on_step_keys=list(dict.fromkeys(payload.depends_on_step_keys)),
        required_action=payload.required_action,
        required_tool_category=payload.required_tool_category,
        inputs=dict(payload.inputs),
        expected_outputs=dict(payload.expected_outputs),
        evidence_refs=list(payload.evidence_refs),
        policy_refs=list(payload.policy_refs),
        risk_level=payload.risk_level,
        approval_required=payload.approval_required,
        approval_type=payload.approval_type,
        recipient_employee_ids=list(payload.recipient_employee_ids),
        created_at=created_at or now,
        updated_at=now,
    )


class SqlAlchemyWorkflowPlanRepository(WorkflowPlanRepository):
    """Postgres/SQLite persistence. Creating rows does not execute steps."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_process_binding(self, process_id: UUID) -> ProcessBindingRecord | None:
        result = await self._session.execute(select(Process).where(Process.id == process_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        context = row.process_context if isinstance(row.process_context, dict) else {}
        schema_version = context.get("schema_version") if isinstance(context, dict) else None
        return ProcessBindingRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            process_context_schema_version=str(schema_version) if schema_version else None,
        )

    async def register_process(
        self,
        process_id: UUID,
        tenant_id: UUID,
        *,
        process_context_schema_version: str | None = None,
    ) -> ProcessBindingRecord:
        existing = await self.get_process_binding(process_id)
        if existing is not None:
            return existing
        now = _utc_now()
        row = Process(
            id=process_id,
            name=f"process-{process_id}",
            process_type="procurement",
            status="draft",
            tenant_id=tenant_id,
            process_context={
                "process_id": str(process_id),
                "tenant_id": str(tenant_id),
                "schema_version": process_context_schema_version or "1.0.0",
            },
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return ProcessBindingRecord(
            id=process_id,
            tenant_id=tenant_id,
            process_context_schema_version=process_context_schema_version,
        )

    async def insert_plan(self, plan: WorkflowPlanRecord) -> WorkflowPlanRecord:
        now = _utc_now()
        row = WorkflowPlan(
            id=plan.id,
            tenant_id=plan.tenant_id,
            process_id=plan.process_id,
            version=plan.version,
            status=plan.status.value,
            created_by_agent=plan.created_by_agent or CREATED_BY_AGENT4,
            source_process_context_schema_version=plan.source_process_context_schema_version,
            source_process_context_ref=plan.source_process_context_ref,
            created_at=plan.created_at or now,
            updated_at=plan.updated_at or now,
        )
        self._session.add(row)
        for step in plan.steps:
            self._session.add(_step_row(step, created_at=step.created_at or now))
        await self._session.flush()
        for step in plan.steps:
            await self._sync_dependencies(plan.tenant_id, plan.id, step)
        await self._session.flush()
        return await self.get_plan(plan.id, tenant_id=plan.tenant_id)

    async def get_plan(
        self, workflow_plan_id: UUID, *, tenant_id: UUID | None = None
    ) -> WorkflowPlanRecord:
        stmt = select(WorkflowPlan).where(WorkflowPlan.id == workflow_plan_id)
        if tenant_id is not None:
            stmt = stmt.where(WorkflowPlan.tenant_id == tenant_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            raise WorkflowPlanNotFoundError(workflow_plan_id)
        return await self._to_plan_record(row)

    async def list_plans_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[WorkflowPlanRecord]:
        result = await self._session.execute(
            select(WorkflowPlan)
            .where(WorkflowPlan.tenant_id == tenant_id, WorkflowPlan.process_id == process_id)
            .order_by(WorkflowPlan.version)
        )
        return [await self._to_plan_record(row) for row in result.scalars().all()]

    async def get_active_plan(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> WorkflowPlanRecord | None:
        result = await self._session.execute(
            select(WorkflowPlan).where(
                WorkflowPlan.tenant_id == tenant_id,
                WorkflowPlan.process_id == process_id,
                WorkflowPlan.status == WorkflowPlanStatus.ACTIVE.value,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return await self._to_plan_record(row)

    async def get_plan_version(
        self, *, tenant_id: UUID, process_id: UUID, version: int
    ) -> WorkflowPlanRecord | None:
        result = await self._session.execute(
            select(WorkflowPlan).where(
                WorkflowPlan.tenant_id == tenant_id,
                WorkflowPlan.process_id == process_id,
                WorkflowPlan.version == version,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return await self._to_plan_record(row)

    async def update_plan_status(
        self, workflow_plan_id: UUID, status: WorkflowPlanStatus, *, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        result = await self._session.execute(
            select(WorkflowPlan).where(
                WorkflowPlan.id == workflow_plan_id, WorkflowPlan.tenant_id == tenant_id
            )
        )
        row = result.scalar_one()
        row.status = status.value
        row.updated_at = _utc_now()
        if status == WorkflowPlanStatus.ACTIVE:
            await self._mark_steps_ready(plan)
        await self._session.flush()
        return await self.get_plan(workflow_plan_id, tenant_id=tenant_id)

    async def add_step(
        self, workflow_plan_id: UUID, payload: CreateWorkflowStepInput, *, tenant_id: UUID
    ) -> WorkflowStepRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        if any(step.step_key == payload.step_key for step in plan.steps):
            raise DuplicateStepKeyError(f"Duplicate step_key '{payload.step_key}'")
        step = _step_from_input(plan, payload)
        self._session.add(_step_row(step))
        await self._session.flush()
        await self._sync_dependencies(tenant_id, workflow_plan_id, step)
        await self._session.flush()
        return step

    async def replace_step(
        self, workflow_plan_id: UUID, payload: CreateWorkflowStepInput, *, tenant_id: UUID
    ) -> WorkflowStepRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        existing = next((s for s in plan.steps if s.step_key == payload.step_key), None)
        if existing is None:
            raise WorkflowStepNotFoundError(payload.step_key)
        step = _step_from_input(plan, payload, step_id=existing.id, created_at=existing.created_at)
        result = await self._session.execute(
            select(WorkflowStep).where(WorkflowStep.id == existing.id)
        )
        row = result.scalar_one()
        _apply_step_row(row, step)
        await self._session.execute(
            delete(WorkflowStepDependency).where(WorkflowStepDependency.step_id == existing.id)
        )
        await self._session.flush()
        await self._sync_dependencies(tenant_id, workflow_plan_id, step)
        await self._session.flush()
        return step

    async def add_dependency(
        self,
        *,
        tenant_id: UUID,
        workflow_plan_id: UUID,
        step_key: str,
        depends_on_step_key: str,
    ) -> None:
        if step_key == depends_on_step_key:
            raise DuplicateDependencyError("A step cannot depend on itself")
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        keys = {step.step_key: step for step in plan.steps}
        if step_key not in keys:
            raise WorkflowStepNotFoundError(step_key)
        if depends_on_step_key not in keys:
            raise WorkflowStepNotFoundError(depends_on_step_key)
        step = keys[step_key]
        if depends_on_step_key in step.depends_on_step_keys:
            raise DuplicateDependencyError(
                f"Duplicate dependency {step_key} -> {depends_on_step_key}"
            )
        step.depends_on_step_keys.append(depends_on_step_key)
        await self._sync_dependencies(tenant_id, workflow_plan_id, step)
        await self._session.flush()

    async def list_steps(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> list[WorkflowStepRecord]:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        return plan.steps

    async def update_step_status(
        self,
        workflow_plan_id: UUID,
        workflow_step_id: UUID,
        status: WorkflowStepStatus,
        *,
        tenant_id: UUID,
    ) -> WorkflowStepRecord:
        result = await self._session.execute(
            select(WorkflowStep).where(
                WorkflowStep.id == workflow_step_id,
                WorkflowStep.workflow_plan_id == workflow_plan_id,
                WorkflowStep.tenant_id == tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise WorkflowStepNotFoundError(str(workflow_step_id))
        row.status = status.value
        row.updated_at = _utc_now()
        await self._session.flush()
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        return next(step for step in plan.steps if step.id == workflow_step_id)

    async def claim_step_execution(
        self, workflow_plan_id: UUID, workflow_step_id: UUID, *, tenant_id: UUID
    ) -> bool:
        result = await self._session.execute(
            select(WorkflowStep)
            .where(
                WorkflowStep.id == workflow_step_id,
                WorkflowStep.workflow_plan_id == workflow_plan_id,
                WorkflowStep.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise WorkflowStepNotFoundError(str(workflow_step_id))
        current = WorkflowStepStatus(row.status)
        if current in {WorkflowStepStatus.IN_PROGRESS, WorkflowStepStatus.COMPLETED}:
            return False
        if current not in {
            WorkflowStepStatus.READY,
            WorkflowStepStatus.AUTHORIZED,
            WorkflowStepStatus.WAITING_DEPENDENCY,
            WorkflowStepStatus.PENDING,
        }:
            return False
        row.status = WorkflowStepStatus.IN_PROGRESS.value
        row.updated_at = _utc_now()
        await self._session.flush()
        return True

    async def _mark_steps_ready(self, plan: WorkflowPlanRecord) -> None:
        result = await self._session.execute(
            select(WorkflowStep).where(WorkflowStep.workflow_plan_id == plan.id)
        )
        by_id = {step.step_key: step for step in plan.steps}
        for row in result.scalars().all():
            record = by_id.get(row.step_key)
            if record is None:
                continue
            if record.status != WorkflowStepStatus.PENDING:
                continue
            row.status = (
                WorkflowStepStatus.WAITING_DEPENDENCY.value
                if record.depends_on_step_keys
                else WorkflowStepStatus.READY.value
            )
            row.updated_at = _utc_now()

    async def _sync_dependencies(
        self, tenant_id: UUID, workflow_plan_id: UUID, step: WorkflowStepRecord
    ) -> None:
        result = await self._session.execute(
            select(WorkflowStep).where(
                WorkflowStep.workflow_plan_id == workflow_plan_id,
                WorkflowStep.tenant_id == tenant_id,
            )
        )
        by_key = {row.step_key: row for row in result.scalars().all()}
        source = by_key.get(step.step_key)
        if source is None:
            return
        for dep_key in step.depends_on_step_keys:
            target = by_key.get(dep_key)
            if target is None:
                raise WorkflowStepNotFoundError(dep_key)
            if target.tenant_id != tenant_id or source.tenant_id != tenant_id:
                raise DuplicateDependencyError("Cross-tenant dependency rejected")
            if target.workflow_plan_id != workflow_plan_id:
                raise DuplicateDependencyError("Dependency must belong to the same plan")
            exists = await self._session.execute(
                select(WorkflowStepDependency).where(
                    WorkflowStepDependency.step_id == source.id,
                    WorkflowStepDependency.depends_on_step_id == target.id,
                )
            )
            if exists.scalar_one_or_none() is not None:
                continue
            self._session.add(
                WorkflowStepDependency(
                    tenant_id=tenant_id,
                    workflow_plan_id=workflow_plan_id,
                    step_id=source.id,
                    depends_on_step_id=target.id,
                )
            )

    async def _to_plan_record(self, row: WorkflowPlan) -> WorkflowPlanRecord:
        steps = await self._load_steps(row.id, row.tenant_id)
        return WorkflowPlanRecord(
            id=row.id,
            tenant_id=row.tenant_id,
            process_id=row.process_id,
            version=row.version,
            status=WorkflowPlanStatus(row.status),
            created_by_agent=row.created_by_agent,
            source_process_context_schema_version=row.source_process_context_schema_version,
            source_process_context_ref=row.source_process_context_ref,
            steps=steps,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _load_steps(self, plan_id: UUID, tenant_id: UUID) -> list[WorkflowStepRecord]:
        result = await self._session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.workflow_plan_id == plan_id, WorkflowStep.tenant_id == tenant_id)
            .order_by(WorkflowStep.sequence)
        )
        rows = list(result.scalars().all())
        dep_result = await self._session.execute(
            select(WorkflowStepDependency).where(
                WorkflowStepDependency.workflow_plan_id == plan_id,
                WorkflowStepDependency.tenant_id == tenant_id,
            )
        )
        id_to_key = {row.id: row.step_key for row in rows}
        deps: dict[UUID, list[str]] = {row.id: [] for row in rows}
        for edge in dep_result.scalars().all():
            dep_key = id_to_key.get(edge.depends_on_step_id)
            if dep_key:
                deps.setdefault(edge.step_id, []).append(dep_key)
        return [_step_record(row, deps.get(row.id, [])) for row in rows]


def _step_row(step: WorkflowStepRecord, *, created_at: datetime | None = None) -> WorkflowStep:
    now = _utc_now()
    return WorkflowStep(
        id=step.id,
        tenant_id=step.tenant_id,
        workflow_plan_id=step.workflow_plan_id,
        step_key=step.step_key,
        sequence=step.sequence,
        name=step.name,
        description=step.description,
        step_type=step.step_type.value if isinstance(step.step_type, WorkflowStepType) else step.step_type,
        status=step.status.value if isinstance(step.status, WorkflowStepStatus) else step.status,
        responsible_employee_id=step.responsible_employee_id,
        responsible_resource_id=step.responsible_resource_id,
        responsible_role_id=step.responsible_role_id,
        responsible_department_id=step.responsible_department_id,
        assignment_unresolved=step.assignment_unresolved,
        unresolved_reason=step.unresolved_reason,
        required_action=step.required_action,
        required_tool_category=step.required_tool_category,
        inputs=dict(step.inputs),
        expected_outputs=dict(step.expected_outputs),
        evidence_refs=[item.model_dump(mode="json") for item in step.evidence_refs],
        policy_refs=[item.model_dump(mode="json") for item in step.policy_refs],
        risk_level=step.risk_level,
        approval_required=step.approval_required,
        approval_type=step.approval_type,
        recipient_employee_ids=[str(item) for item in step.recipient_employee_ids],
        created_at=created_at or step.created_at or now,
        updated_at=step.updated_at or now,
    )


def _apply_step_row(row: WorkflowStep, step: WorkflowStepRecord) -> None:
    row.sequence = step.sequence
    row.name = step.name
    row.description = step.description
    row.step_type = step.step_type.value
    row.status = step.status.value
    row.responsible_employee_id = step.responsible_employee_id
    row.responsible_resource_id = step.responsible_resource_id
    row.responsible_role_id = step.responsible_role_id
    row.responsible_department_id = step.responsible_department_id
    row.assignment_unresolved = step.assignment_unresolved
    row.unresolved_reason = step.unresolved_reason
    row.required_action = step.required_action
    row.required_tool_category = step.required_tool_category
    row.inputs = dict(step.inputs)
    row.expected_outputs = dict(step.expected_outputs)
    row.evidence_refs = [item.model_dump(mode="json") for item in step.evidence_refs]
    row.policy_refs = [item.model_dump(mode="json") for item in step.policy_refs]
    row.risk_level = step.risk_level
    row.approval_required = step.approval_required
    row.approval_type = step.approval_type
    row.recipient_employee_ids = [str(item) for item in step.recipient_employee_ids]
    row.updated_at = _utc_now()


def _step_record(row: WorkflowStep, depends_on: list[str]) -> WorkflowStepRecord:
    evidence = [
        WorkflowEvidenceRef.model_validate(item) if not isinstance(item, WorkflowEvidenceRef) else item
        for item in (row.evidence_refs or [])
    ]
    policies = [
        WorkflowPolicyRef.model_validate(item) if not isinstance(item, WorkflowPolicyRef) else item
        for item in (row.policy_refs or [])
    ]
    recipients: list[UUID] = []
    for item in row.recipient_employee_ids or []:
        recipients.append(item if isinstance(item, UUID) else UUID(str(item)))
    return WorkflowStepRecord(
        id=row.id,
        tenant_id=row.tenant_id,
        workflow_plan_id=row.workflow_plan_id,
        step_key=row.step_key,
        sequence=row.sequence,
        name=row.name,
        description=row.description,
        step_type=WorkflowStepType(row.step_type),
        status=WorkflowStepStatus(row.status),
        responsible_employee_id=row.responsible_employee_id,
        responsible_resource_id=row.responsible_resource_id,
        responsible_role_id=row.responsible_role_id,
        responsible_department_id=row.responsible_department_id,
        assignment_unresolved=row.assignment_unresolved,
        unresolved_reason=row.unresolved_reason,
        depends_on_step_keys=depends_on,
        required_action=row.required_action,
        required_tool_category=row.required_tool_category,
        inputs=dict(row.inputs or {}),
        expected_outputs=dict(row.expected_outputs or {}),
        evidence_refs=evidence,
        policy_refs=policies,
        risk_level=row.risk_level,
        approval_required=row.approval_required,
        approval_type=row.approval_type,
        recipient_employee_ids=recipients,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
