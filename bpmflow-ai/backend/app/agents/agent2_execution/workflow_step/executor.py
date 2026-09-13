"""Execute exactly one authorized WorkflowStep. Never plans or chains tools."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent2_execution.execution.execution_engine import execute_with_recovery
from app.agents.agent2_execution.execution.idempotency import generate_idempotency_key
from app.agents.agent2_execution.security.audit import log_audit_event
from app.agents.agent2_execution.security.tool_guard import ExecutionGuardContext
from app.agents.agent2_execution.tools import registry as agent2_tool_registry
from app.agents.agent2_execution.workflow_step.exceptions import (
    CrossTenantDeniedError,
    DependencyNotCompletedError,
    HumanApprovalRequiredError,
    InvalidToolInputError,
    MissingRequiredExecutionContextError,
    NotAuthorizedError,
    PlanNotExecutableError,
    StepAlreadyInProgressError,
    StepNotExecutableError,
    UnknownWorkflowStepError,
    WorkflowStepExecutionError,
)
from app.agents.agent2_execution.workflow_step.inputs import (
    build_tool_parameters,
    reject_conflicting_overrides,
)
from app.agents.agent2_execution.workflow_step.schemas import (
    WorkflowStepExecutionRequest,
    WorkflowStepExecutionResult,
)
from app.agents.agent4_orchestrator.constants import WorkflowStage
from app.agents.agent4_orchestrator.workflow_plan.constants import (
    WorkflowPlanStatus,
    WorkflowStepStatus,
    WorkflowStepType,
)
from app.agents.agent4_orchestrator.workflow_plan.exceptions import WorkflowPlanNotFoundError
from app.agents.agent4_orchestrator.workflow_plan.schemas import WorkflowPlanRecord, WorkflowStepRecord
from app.agents.agent4_orchestrator.workflow_plan.service import WorkflowPlanService
from app.process_context.service import context_from_process_row
from app.tool_registry.exceptions import ToolRegistryError
from app.tool_registry.service import ToolRegistryService

EXECUTABLE_PLAN_STATUSES = frozenset({WorkflowPlanStatus.ACTIVE})
TERMINAL_STEP_STATUSES = frozenset(
    {
        WorkflowStepStatus.COMPLETED,
        WorkflowStepStatus.FAILED,
        WorkflowStepStatus.SKIPPED,
        WorkflowStepStatus.CANCELLED,
        WorkflowStepStatus.EXCEPTION,
    }
)


class WorkflowStepExecutor:
    def __init__(
        self,
        *,
        plan_service: WorkflowPlanService,
        process_repository: Any,
        tool_registry: ToolRegistryService,
        directory: Any | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._plans = plan_service
        self._processes = process_repository
        self._tools = tool_registry
        self._directory = directory
        self._session = session

    async def execute_one_step(
        self, request: WorkflowStepExecutionRequest, *, tenant_id: UUID
    ) -> WorkflowStepExecutionResult:
        trace_id = request.trace_id or f"trace-{uuid4().hex[:12]}"
        try:
            plan = await self._plans.get_plan(request.workflow_plan_id, tenant_id=tenant_id)
        except WorkflowPlanNotFoundError as exc:
            raise CrossTenantDeniedError("Workflow plan is not visible to this tenant") from exc
        step = self._step_from_plan(plan, request.workflow_step_id)
        process = await self._processes.get_process(request.process_id)
        self._assert_tenancy(tenant_id, plan, step, process)
        if plan.process_id != request.process_id or step.workflow_plan_id != plan.id:
            raise CrossTenantDeniedError("Workflow step does not belong to the requested process/plan")
        if plan.status not in EXECUTABLE_PLAN_STATUSES:
            raise PlanNotExecutableError(
                f"Workflow plan status {plan.status.value} is not executable"
            )
        context = context_from_process_row(process)
        if context.tenant_id is not None and context.tenant_id != tenant_id:
            raise CrossTenantDeniedError("ProcessContext tenant mismatch")
        ref = request.process_context_ref or context.process_id
        if ref != context.process_id and ref != request.process_id:
            raise MissingRequiredExecutionContextError(
                "process_context_ref does not match ProcessContext"
            )

        if step.status is WorkflowStepStatus.WAITING_HUMAN_APPROVAL or (
            step.step_type is WorkflowStepType.APPROVAL
            and step.status is not WorkflowStepStatus.COMPLETED
        ):
            raise HumanApprovalRequiredError(
                "Human approval is required; Agent 2 cannot approve this step"
            )
        if step.status in TERMINAL_STEP_STATUSES and step.status is not WorkflowStepStatus.COMPLETED:
            raise StepNotExecutableError(f"Step status {step.status.value} cannot execute")
        self._assert_dependencies_completed(plan, step)

        if step.status is WorkflowStepStatus.COMPLETED:
            return await self._replay_completed(request, plan, step, trace_id)

        stage = getattr(process.current_stage, "value", str(process.current_stage or ""))
        if str(stage).upper() != WorkflowStage.WORKFLOW_EXECUTION.value:
            raise NotAuthorizedError(
                "Mutating WorkflowStep execution requires process stage WORKFLOW_EXECUTION"
            )
        if request.authorization_state != "AUTHORIZED":
            raise NotAuthorizedError("Workflow step is not authorized for execution")

        try:
            tool_record = await self._tools.resolve_for_step(tenant_id=tenant_id, workflow_step=step)
        except ToolRegistryError as exc:
            raise WorkflowStepExecutionError(str(exc), error_code=exc.error_code) from exc
        binding = self._tools.implementation_for(tool_record)
        tool_name = binding.agent2_tool_name
        reject_conflicting_overrides(context=context, caller_parameters=request.caller_parameters)
        parameters = build_tool_parameters(
            context=context,
            step=step,
            process_id=request.process_id,
            task_id=str(step.id),
            directory=self._directory,
        )
        self._validate_tool_input(tool_name, parameters)

        idempotency_key = request.idempotency_key or generate_idempotency_key(
            str(request.process_id), str(step.id), tool_name
        )
        from app.agents.agent2_execution.database.persistence import (
            ensure_process_instance,
            ensure_task,
        )

        if self._session is not None:
            await ensure_process_instance(
                self._session,
                str(request.process_id),
                title=getattr(process, "name", None) or "process",
                process_type=getattr(process, "process_type", None) or "procurement",
            )
            await ensure_task(
                self._session,
                str(request.process_id),
                str(step.id),
                title=step.name,
                task_type=step.step_type.value,
            )

        claimed = await self._plans.claim_step_execution(
            plan.id, step.id, tenant_id=tenant_id
        )
        if not claimed:
            refreshed = await self._plans.get_plan(plan.id, tenant_id=tenant_id)
            current = self._step_from_plan(refreshed, step.id)
            if current.status is WorkflowStepStatus.COMPLETED:
                return await self._replay_completed(request, refreshed, current, trace_id)
            raise StepAlreadyInProgressError("Workflow step is already in progress")

        await log_audit_event(
            self._session,
            actor="agent_2",
            action=tool_name,
            allowed=True,
            reason="one_step_execution_start",
            payload={
                "tenant_id": str(tenant_id),
                "process_id": str(request.process_id),
                "workflow_plan_id": str(plan.id),
                "workflow_step_id": str(step.id),
                "trace_id": trace_id,
                "action_code": step.required_action,
            },
        )
        receipt = await execute_with_recovery(
            process_id=str(request.process_id),
            task_id=str(step.id),
            tool_name=tool_name,
            parameters=parameters,
            session=self._session,
            actor="agent_2",
            idempotency_key=idempotency_key,
            directory=self._directory,
            guard_context=ExecutionGuardContext(
                message_status="AUTHORIZED",
                process_stage=WorkflowStage.WORKFLOW_EXECUTION.value,
                process_id=str(request.process_id),
                tenant_id=str(tenant_id),
                workflow_plan_id=str(plan.id),
                workflow_step_id=str(step.id),
            ),
        )
        success = receipt.status == "SUCCESS"
        next_status = WorkflowStepStatus.COMPLETED if success else WorkflowStepStatus.FAILED
        if success and (step.required_action or "").strip().upper() == "MATCH_INVOICE":
            if (receipt.result or {}).get("matched") is False:
                next_status = WorkflowStepStatus.EXCEPTION
        await self._plans.update_step_status(
            plan.id, step.id, next_status, tenant_id=tenant_id
        )
        result_payload = dict(receipt.result or {})
        result_payload.update(
            {
                "workflow_plan_id": str(plan.id),
                "workflow_step_id": str(step.id),
                "implementation_key": binding.implementation_key,
                "trace_id": trace_id,
            }
        )
        return WorkflowStepExecutionResult(
            execution_status=receipt.status,
            workflow_plan_id=plan.id,
            workflow_step_id=step.id,
            process_id=request.process_id,
            action_code=step.required_action,
            tool_name=tool_name,
            implementation_key=binding.implementation_key,
            receipt_id=receipt.id,
            step_status=next_status.value,
            result=result_payload,
            error_code=None if success else (receipt.error_type or "TOOL_EXECUTION_FAILED"),
            error_message=None if success else (receipt.error_message or None),
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            duplicate=False,
        )

    def _step_from_plan(self, plan: WorkflowPlanRecord, step_id: UUID) -> WorkflowStepRecord:
        for step in plan.steps:
            if step.id == step_id:
                return step
        raise UnknownWorkflowStepError(step_id)

    def _assert_tenancy(self, tenant_id: UUID, plan, step, process) -> None:
        process_tenant = getattr(process, "tenant_id", None)
        if plan.tenant_id != tenant_id:
            raise CrossTenantDeniedError("Workflow plan belongs to another tenant")
        if step.tenant_id != tenant_id:
            raise CrossTenantDeniedError("Workflow step belongs to another tenant")
        if process_tenant is not None and process_tenant != tenant_id:
            raise CrossTenantDeniedError("Process belongs to another tenant")

    def _assert_dependencies_completed(
        self, plan: WorkflowPlanRecord, step: WorkflowStepRecord
    ) -> None:
        by_key = {item.step_key: item for item in plan.steps}
        for dep_key in step.depends_on_step_keys:
            dep = by_key.get(dep_key)
            if dep is None or dep.tenant_id != plan.tenant_id or dep.workflow_plan_id != plan.id:
                raise DependencyNotCompletedError(
                    f"Dependency '{dep_key}' is missing from this plan"
                )
            if dep.status is WorkflowStepStatus.WAITING_HUMAN_APPROVAL:
                raise HumanApprovalRequiredError(
                    f"Dependency '{dep_key}' is waiting for human approval"
                )
            if dep.status is not WorkflowStepStatus.COMPLETED:
                raise DependencyNotCompletedError(
                    f"Dependency '{dep_key}' is {dep.status.value}, not COMPLETED"
                )

    def _validate_tool_input(self, tool_name: str, parameters: dict[str, Any]) -> None:
        try:
            definition = agent2_tool_registry.get(tool_name)
            if definition is None:
                raise InvalidToolInputError(
                    f"Agent 2 has no allow-listed handler for {tool_name}"
                )
        except Exception as exc:
            raise InvalidToolInputError(
                f"Agent 2 has no allow-listed handler for {tool_name}"
            ) from exc
        try:
            definition.input_schema.model_validate(parameters)
        except Exception as exc:
            raise InvalidToolInputError(str(exc)) from exc

    async def _replay_completed(
        self,
        request: WorkflowStepExecutionRequest,
        plan: WorkflowPlanRecord,
        step: WorkflowStepRecord,
        trace_id: str,
    ) -> WorkflowStepExecutionResult:
        tool_name = None
        implementation_key = None
        resolution = (step.inputs or {}).get("tool_resolution") or {}
        if isinstance(resolution, dict):
            tool_name = resolution.get("agent2_tool_name") or resolution.get("tool_name")
            implementation_key = resolution.get("implementation_key")
        idempotency_key = request.idempotency_key or generate_idempotency_key(
            str(request.process_id), str(step.id), tool_name or "create_po_draft"
        )
        from app.agents.agent2_execution.execution import idempotency

        existing = await idempotency.check_existing_receipt(self._session, idempotency_key)
        return WorkflowStepExecutionResult(
            execution_status="SUCCESS" if existing else "COMPLETED",
            workflow_plan_id=plan.id,
            workflow_step_id=step.id,
            process_id=request.process_id,
            action_code=step.required_action,
            tool_name=tool_name,
            implementation_key=implementation_key,
            receipt_id=None if existing is None else existing.id,
            step_status=WorkflowStepStatus.COMPLETED.value,
            result=dict(existing.result or {}) if existing is not None else {},
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            duplicate=True,
        )
