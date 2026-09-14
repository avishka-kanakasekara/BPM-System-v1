"""Agent 4 WorkflowPlan service: draft, validate, activate. No execution."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.company_directory.service import CompanyDirectoryService

from .constants import MUTABLE_PLAN_STATUSES, CREATED_BY_AGENT4, WorkflowPlanStatus, WorkflowStepStatus, WorkflowStepType
from .exceptions import (
    CrossTenantWorkflowError,
    PlanNotMutableError,
    WorkflowPlanError,
    WorkflowPlanNotFoundError,
    WorkflowStepNotFoundError,
)
from .repository import ProcessBindingRecord, WorkflowPlanRepository
from .schemas import (
    CreateWorkflowPlanInput,
    CreateWorkflowStepInput,
    WorkflowPlanRecord,
    WorkflowPlanValidationResult,
    WorkflowStepRecord,
)
from .validator import WorkflowPlanValidator


class WorkflowPlanService:
    """Agent 4 owns plan lifecycle. Activation is not step execution."""

    def __init__(
        self,
        repository: WorkflowPlanRepository,
        *,
        directory: CompanyDirectoryService | None = None,
        validator: WorkflowPlanValidator | None = None,
    ) -> None:
        self._repo = repository
        self._directory = directory
        self._validator = validator or WorkflowPlanValidator(directory)

    async def create_draft(
        self, payload: CreateWorkflowPlanInput, *, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        binding = await self._require_process(payload.process_id, tenant_id)
        existing = await self._repo.list_plans_for_process(
            tenant_id=tenant_id, process_id=payload.process_id
        )
        version = (max((plan.version for plan in existing), default=0) + 1)
        schema_version = (
            payload.source_process_context_schema_version
            or binding.process_context_schema_version
        )
        plan = WorkflowPlanRecord(
            id=uuid4(),
            tenant_id=tenant_id,
            process_id=payload.process_id,
            version=version,
            status=WorkflowPlanStatus.DRAFT,
            created_by_agent=CREATED_BY_AGENT4,
            source_process_context_schema_version=schema_version,
            source_process_context_ref=payload.source_process_context_ref or "process_context",
        )
        return await self._repo.insert_plan(plan)

    async def add_step(
        self,
        workflow_plan_id: UUID,
        payload: CreateWorkflowStepInput,
        *,
        tenant_id: UUID,
    ) -> WorkflowStepRecord:
        plan = await self._mutable_plan(workflow_plan_id, tenant_id)
        _ = plan
        return await self._repo.add_step(workflow_plan_id, payload, tenant_id=tenant_id)

    async def update_step(
        self,
        workflow_plan_id: UUID,
        payload: CreateWorkflowStepInput,
        *,
        tenant_id: UUID,
    ) -> WorkflowStepRecord:
        await self._mutable_plan(workflow_plan_id, tenant_id)
        return await self._repo.replace_step(workflow_plan_id, payload, tenant_id=tenant_id)

    async def add_dependency(
        self,
        *,
        tenant_id: UUID,
        workflow_plan_id: UUID,
        step_key: str,
        depends_on_step_key: str,
    ) -> WorkflowPlanRecord:
        await self._mutable_plan(workflow_plan_id, tenant_id)
        await self._repo.add_dependency(
            tenant_id=tenant_id,
            workflow_plan_id=workflow_plan_id,
            step_key=step_key,
            depends_on_step_key=depends_on_step_key,
        )
        return await self._repo.get_plan(workflow_plan_id, tenant_id=tenant_id)

    async def get_plan(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        return await self._repo.get_plan(workflow_plan_id, tenant_id=tenant_id)

    async def get_active_plan(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> WorkflowPlanRecord | None:
        await self._require_process(process_id, tenant_id)
        return await self._repo.get_active_plan(tenant_id=tenant_id, process_id=process_id)

    async def get_plan_version(
        self, *, tenant_id: UUID, process_id: UUID, version: int
    ) -> WorkflowPlanRecord | None:
        await self._require_process(process_id, tenant_id)
        return await self._repo.get_plan_version(
            tenant_id=tenant_id, process_id=process_id, version=version
        )

    async def list_steps(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> list[WorkflowStepRecord]:
        return await self._repo.list_steps(workflow_plan_id, tenant_id=tenant_id)

    async def update_step_status(
        self,
        workflow_plan_id: UUID,
        workflow_step_id: UUID,
        status: WorkflowStepStatus,
        *,
        tenant_id: UUID,
    ) -> WorkflowStepRecord:
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        _ = plan
        return await self._repo.update_step_status(
            workflow_plan_id, workflow_step_id, status, tenant_id=tenant_id
        )

    async def claim_step_execution(
        self, workflow_plan_id: UUID, workflow_step_id: UUID, *, tenant_id: UUID
    ) -> bool:
        await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        return await self._repo.claim_step_execution(
            workflow_plan_id, workflow_step_id, tenant_id=tenant_id
        )

    async def complete_human_step(
        self, workflow_plan_id: UUID, workflow_step_id: UUID, *, tenant_id: UUID
    ) -> WorkflowStepRecord:
        """Record a genuine human/manual completion. Never used for SYSTEM_ACTION tools."""
        plan = await self.get_plan(workflow_plan_id, tenant_id=tenant_id)
        step = next((item for item in plan.steps if item.id == workflow_step_id), None)
        if step is None:
            raise WorkflowStepNotFoundError(str(workflow_step_id))
        if step.step_type is WorkflowStepType.SYSTEM_ACTION:
            raise WorkflowPlanError(
                "SYSTEM_ACTION steps cannot be completed by the human approval path",
                error_code="STEP_NOT_EXECUTABLE",
            )
        updated = await self._repo.update_step_status(
            workflow_plan_id,
            workflow_step_id,
            WorkflowStepStatus.COMPLETED,
            tenant_id=tenant_id,
        )
        try:
            from datetime import UTC, datetime

            from app.monitoring.recorder import record_step_execution

            now = datetime.now(UTC)
            record_step_execution(
                process_id=plan.process_id,
                tenant_id=tenant_id,
                workflow_plan_id=plan.id,
                workflow_step_id=step.id,
                name=step.name,
                step_type=step.step_type.value,
                status=WorkflowStepStatus.COMPLETED.value,
                started_at=now,
                ended_at=now,
                step_key=step.step_key,
                depends_on_step_keys=list(step.depends_on_step_keys or []),
                approval_required=bool(step.approval_required) or step.step_type is WorkflowStepType.APPROVAL,
                actor="human",
            )
        except Exception:
            pass
        return updated

    async def list_plans_for_process(
        self, *, tenant_id: UUID, process_id: UUID
    ) -> list[WorkflowPlanRecord]:
        await self._require_process(process_id, tenant_id)
        return await self._repo.list_plans_for_process(tenant_id=tenant_id, process_id=process_id)

    async def validate(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> WorkflowPlanValidationResult:
        plan = await self._repo.get_plan(workflow_plan_id, tenant_id=tenant_id)
        binding = await self._require_process(plan.process_id, tenant_id)
        return self._validator.validate(plan, process=binding)

    async def activate(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        plan = await self._mutable_plan(workflow_plan_id, tenant_id)
        result = await self.validate(workflow_plan_id, tenant_id=tenant_id)
        if not result.valid:
            raise WorkflowPlanError(
                "Only a valid workflow plan can become ACTIVE",
                error_code="PLAN_NOT_VALID",
            )
        current_active = await self._repo.get_active_plan(
            tenant_id=tenant_id, process_id=plan.process_id
        )
        if current_active is not None and current_active.id == plan.id:
            raise PlanNotMutableError("Active plan cannot be silently overwritten")
        if current_active is not None:
            await self._repo.update_plan_status(
                current_active.id, WorkflowPlanStatus.SUPERSEDED, tenant_id=tenant_id
            )
        return await self._repo.update_plan_status(
            plan.id, WorkflowPlanStatus.ACTIVE, tenant_id=tenant_id
        )

    async def mark_ready(
        self, workflow_plan_id: UUID, *, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        result = await self.validate(workflow_plan_id, tenant_id=tenant_id)
        if not result.valid:
            raise WorkflowPlanError(
                "Only a valid workflow plan can become READY",
                error_code="PLAN_VALIDATION_FAILED",
            )
        return await self._repo.update_plan_status(
            workflow_plan_id, WorkflowPlanStatus.READY, tenant_id=tenant_id
        )

    async def _mutable_plan(
        self, workflow_plan_id: UUID, tenant_id: UUID
    ) -> WorkflowPlanRecord:
        plan = await self._repo.get_plan(workflow_plan_id, tenant_id=tenant_id)
        if plan.status not in MUTABLE_PLAN_STATUSES:
            raise PlanNotMutableError(
                f"Workflow plan {workflow_plan_id} is {plan.status.value} and cannot be modified"
            )
        return plan

    async def _require_process(
        self, process_id: UUID, tenant_id: UUID
    ) -> ProcessBindingRecord:
        binding = await self._repo.get_process_binding(process_id)
        if binding is None:
            from app.agents.agent4_orchestrator.exceptions import ProcessNotFoundError

            raise ProcessNotFoundError(process_id)
        if binding.tenant_id is None or binding.tenant_id != tenant_id:
            raise CrossTenantWorkflowError(
                "Process does not belong to this tenant",
                error_code="CROSS_TENANT_DENIED",
            )
        return binding
