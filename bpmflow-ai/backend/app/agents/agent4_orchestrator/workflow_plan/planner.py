"""Deterministic Agent 4 workflow planner. Creates plans; never executes tools."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.agents.agent3_resources.interfaces import InMemoryResourceRepository
from app.agents.agent3_resources.schemas import (
    AgentMessageMetadata as Agent3Metadata,
)
from app.agents.agent3_resources.schemas import AllocationRequest, HumanResourceRequirement
from app.agents.agent3_resources.constants import MessageType as Agent3MessageType
from app.agents.agent3_resources.service import ResourceAllocationService
from app.company_directory.schemas import EmployeeRecord
from app.company_directory.service import CompanyDirectoryService
from app.policy_knowledge.constants import PolicyOperator, PolicyRetrievalStatus, PolicyRuleType
from app.policy_knowledge.retrieval import PolicyRetrievalService
from app.policy_knowledge.schemas import PolicyRiskSnapshot, PolicyRule
from app.process_context.schemas import ProcessContext
from app.process_context.service import context_from_process_row
from app.tool_registry.exceptions import (
    ToolAmbiguousError,
    ToolCategoryMismatchError,
    ToolDisabledError,
    ToolNotRegisteredError,
    ToolStepTypeNotAllowedError,
)
from app.tool_registry.service import ToolRegistryService

from .constants import WorkflowPlanStatus, WorkflowStepStatus, WorkflowStepType
from .planning_schemas import PlanningIssue, WorkflowPlanningResult
from .schemas import (
    CreateWorkflowPlanInput,
    CreateWorkflowStepInput,
    WorkflowEvidenceRef,
    WorkflowPolicyRef,
)
from .service import WorkflowPlanService

INVENTED_SKILLS = frozenset({"python", "fastapi", "developer", "javascript", "java", "react"})


class WorkflowPlanner:
    """Agent 4 control-plane planner. LLM has no authority here."""

    def __init__(
        self,
        *,
        plan_service: WorkflowPlanService,
        process_repository: Any,
        policy_retrieval: PolicyRetrievalService | None,
        tool_registry: ToolRegistryService,
        directory: CompanyDirectoryService,
        allocator: ResourceAllocationService | None = None,
    ) -> None:
        self._plans = plan_service
        self._processes = process_repository
        self._policy = policy_retrieval
        self._tools = tool_registry
        self._directory = directory
        self._allocator = allocator or ResourceAllocationService(
            InMemoryResourceRepository(), directory=directory
        )

    async def generate_plan(
        self, *, process_id: UUID, tenant_id: UUID
    ) -> WorkflowPlanningResult:
        issues: list[PlanningIssue] = []
        process = await self._processes.get_process(process_id)
        if process.tenant_id is not None and process.tenant_id != tenant_id:
            issues.append(
                PlanningIssue(code="CROSS_TENANT_DENIED", message="Process belongs to another tenant")
            )
            return WorkflowPlanningResult(
                process_id=process_id, tenant_id=tenant_id, issues=issues
            )
        ctx = context_from_process_row(process)
        if ctx.tenant_id is not None and ctx.tenant_id != tenant_id:
            issues.append(
                PlanningIssue(code="CROSS_TENANT_DENIED", message="ProcessContext tenant mismatch")
            )
            return WorkflowPlanningResult(
                process_id=process_id, tenant_id=tenant_id, issues=issues
            )

        issues.extend(self._required_facts(ctx))
        snapshot = await self._load_policy(tenant_id, ctx, issues)
        if any(item.blocking and item.code == "POLICY_NOT_FOUND" for item in issues):
            return await self._persist_failed_draft(
                process_id, tenant_id, ctx, issues, snapshot
            )

        if ctx.purchase.amount is not None and ctx.purchase.currency:
            self._apply_budget_and_evidence(ctx, snapshot, issues)

        requester = self._requester_employee(tenant_id, ctx)
        procurement = await self._allocate(
            process_id=process_id,
            tenant_id=tenant_id,
            requester_user_id=ctx.requester.user_id or uuid4(),
            requester_employee_id=None if requester is None else requester.employee_id,
            required_roles=["Procurement Officer"],
            required_department_code="PROCUREMENT",
            skills=self._discovery_skills(ctx),
            assignment_kind="allocation",
        )
        if procurement.get("error_code"):
            issues.append(
                PlanningIssue(
                    code=procurement["error_code"],
                    message=procurement.get("error_message") or "No eligible procurement resource",
                )
            )
        officer = procurement.get("candidate")

        approval_types = self._required_approval_types(snapshot, ctx.purchase.amount)
        approvers: dict[str, Any] = {}
        for approval_type in approval_types:
            step_key = f"{approval_type.lower().replace('_', '-')}-approval"
            allocated = await self._allocate(
                process_id=process_id,
                tenant_id=tenant_id,
                requester_user_id=ctx.requester.user_id or uuid4(),
                requester_employee_id=None if requester is None else requester.employee_id,
                required_roles=[],
                assignment_kind="approver",
                required_approval_type=approval_type,
                minimum_authority_amount=ctx.purchase.amount,
                authority_currency=ctx.purchase.currency,
            )
            candidate = allocated.get("candidate")
            if self._sod_for_approval(
                tenant_id=tenant_id,
                requester=requester,
                approval_type=approval_type,
                amount=ctx.purchase.amount,
                currency=ctx.purchase.currency,
                candidate=candidate,
            ):
                issues.append(
                    PlanningIssue(
                        code="SAME_PERSON",
                        message="Requester cannot approve their own request",
                        step_key=step_key,
                    )
                )
                candidate = None
            elif candidate is None or candidate.employee_id is None:
                issues.append(
                    PlanningIssue(
                        code=allocated.get("error_code") or "APPROVER_NOT_RESOLVED",
                        message=allocated.get("error_message")
                        or f"Approver not resolved for {approval_type}",
                        step_key=step_key,
                    )
                )
                candidate = None
            approvers[approval_type] = candidate

        await self._ensure_plan_process(process_id, tenant_id, ctx)
        draft = await self._plans.create_draft(
            CreateWorkflowPlanInput(
                process_id=process_id,
                source_process_context_schema_version=ctx.schema_version,
                source_process_context_ref="process_context",
            ),
            tenant_id=tenant_id,
        )
        steps = self._build_step_specs(
            ctx=ctx,
            snapshot=snapshot,
            officer=officer,
            approvers=approvers,
            issues=issues,
        )
        for spec in steps:
            await self._attach_tool_resolution(tenant_id, spec, issues)
            await self._plans.add_step(draft.id, spec, tenant_id=tenant_id)

        plan = await self._plans.get_plan(draft.id, tenant_id=tenant_id)
        validation = await self._plans.validate(draft.id, tenant_id=tenant_id)
        if not validation.valid:
            for item in validation.issues:
                issues.append(
                    PlanningIssue(
                        code=item.code if item.code != "WORKFLOW_PLAN_ERROR" else "PLAN_VALIDATION_FAILED",
                        message=item.message,
                        step_key=item.step_key,
                    )
                )
        blocking = [item for item in issues if item.blocking]
        execution_ready = validation.valid and not blocking and not any(
            item.code.startswith("TOOL_") for item in issues
        )
        if validation.valid and not blocking:
            plan = await self._plans.mark_ready(draft.id, tenant_id=tenant_id)
        return WorkflowPlanningResult(
            process_id=process_id,
            tenant_id=tenant_id,
            workflow_plan_id=plan.id,
            version=plan.version,
            status=plan.status.value,
            execution_ready=execution_ready,
            structurally_valid=validation.valid,
            steps=plan.steps,
            issues=issues,
            plan=plan,
            allocations={
                "procurement": None if officer is None else officer.employee_id,
                "approvers": {
                    key: None if value is None else value.employee_id
                    for key, value in approvers.items()
                },
            },
        )

    def _required_facts(self, ctx: ProcessContext) -> list[PlanningIssue]:
        missing: list[str] = []
        if ctx.purchase.amount is None:
            missing.append("purchase.amount")
        if not ctx.purchase.currency:
            missing.append("purchase.currency")
        if missing:
            return [
                PlanningIssue(
                    code="MISSING_REQUIRED_CONTEXT",
                    message=f"Missing required ProcessContext fields: {', '.join(missing)}",
                )
            ]
        return []

    async def _load_policy(
        self, tenant_id: UUID, ctx: ProcessContext, issues: list[PlanningIssue]
    ) -> PolicyRiskSnapshot | None:
        if self._policy is None:
            issues.append(
                PlanningIssue(code="POLICY_NOT_FOUND", message="No policy retrieval service configured")
            )
            return None
        snapshot = await self._policy.build_risk_snapshot(
            tenant_id=tenant_id,
            purchase_amount=ctx.purchase.amount,
            available_budget=ctx.budget.available_amount,
        )
        if snapshot.status in (
            PolicyRetrievalStatus.NOT_FOUND,
            PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE,
            PolicyRetrievalStatus.CONFLICT,
        ):
            issues.append(
                PlanningIssue(
                    code="POLICY_NOT_FOUND",
                    message=snapshot.message or f"Active policy status is {snapshot.status.value}",
                )
            )
        return snapshot

    def _apply_budget_and_evidence(
        self,
        ctx: ProcessContext,
        snapshot: PolicyRiskSnapshot | None,
        issues: list[PlanningIssue],
    ) -> None:
        amount = ctx.purchase.amount
        if amount is None:
            return
        if ctx.budget.available_amount is not None and amount > ctx.budget.available_amount:
            issues.append(
                PlanningIssue(
                    code="INSUFFICIENT_BUDGET",
                    message="Purchase amount exceeds available budget in ProcessContext",
                )
            )
        if snapshot is None:
            return
        for rule in snapshot.rules:
            if rule.rule_type is not PolicyRuleType.REQUIRED_EVIDENCE:
                continue
            if not self._rule_applies(amount, rule):
                continue
            meta = rule.metadata_json or {}
            min_quotes = int(meta.get("min_quotations") or (1 if "quotation" in rule.required_evidence else 0))
            quote_count = ctx.quotation_count
            if ctx.tenant_id is not None:
                try:
                    from app.procurement.service import get_procurement

                    db_count = get_procurement().count_quotations(
                        tenant_id=ctx.tenant_id, process_id=ctx.process_id
                    )
                    if db_count:
                        quote_count = db_count
                except Exception:
                    quote_count = ctx.quotation_count
            if min_quotes and quote_count < min_quotes:
                issues.append(
                    PlanningIssue(
                        code="MISSING_REQUIRED_CONTEXT",
                        message=(
                            f"Policy requires {min_quotes} quotation(s); "
                            f"process has {quote_count}"
                        ),
                    )
                )
            if meta.get("requires_justification") and not (ctx.purchase.description or "").strip():
                issues.append(
                    PlanningIssue(
                        code="MISSING_REQUIRED_CONTEXT",
                        message="Policy requires purchase justification",
                    )
                )
            if meta.get("requires_budget_confirmation") and ctx.budget.available_amount is None:
                issues.append(
                    PlanningIssue(
                        code="MISSING_REQUIRED_CONTEXT",
                        message="Policy requires budget confirmation",
                    )
                )

    def _required_approval_types(
        self, snapshot: PolicyRiskSnapshot | None, amount: Decimal | None
    ) -> list[str]:
        if snapshot is None or amount is None:
            return []
        types: list[str] = []
        for rule in snapshot.rules:
            if rule.rule_type not in (
                PolicyRuleType.APPROVAL_THRESHOLD,
                PolicyRuleType.HIGH_VALUE_THRESHOLD,
                PolicyRuleType.REQUIRED_AUTHORIZATION,
            ):
                continue
            meta = rule.metadata_json or {}
            for band in meta.get("additional_approvals") or []:
                approval = str(band.get("approval") or "").strip().upper()
                if not approval:
                    continue
                if "applies_at_or_below" in band and amount <= Decimal(str(band["applies_at_or_below"])):
                    types.append(approval)
                if "applies_above" in band and amount > Decimal(str(band["applies_above"])):
                    types.append(approval)
            if not self._rule_applies(amount, rule):
                continue
            if rule.required_approval:
                types.append(rule.required_approval.strip().upper())
            for role in rule.required_roles:
                types.append(role.strip().upper())
        unique: list[str] = []
        for item in types:
            if item and item not in unique:
                unique.append(item)
        return unique

    def _rule_applies(self, amount: Decimal, rule: PolicyRule) -> bool:
        meta = rule.metadata_json or {}
        applies_above = meta.get("applies_above")
        if applies_above is not None and amount <= Decimal(str(applies_above)):
            return False
        if rule.threshold_value is None:
            return True
        operator = rule.operator or PolicyOperator.GT
        threshold = rule.threshold_value
        if operator is PolicyOperator.GT:
            return amount > threshold
        if operator is PolicyOperator.GTE:
            return amount >= threshold
        if operator is PolicyOperator.LT:
            return amount < threshold
        if operator is PolicyOperator.LTE:
            return amount <= threshold
        if operator is PolicyOperator.EQ:
            return amount == threshold
        return False

    def _requester_employee(self, tenant_id: UUID, ctx: ProcessContext) -> EmployeeRecord | None:
        if ctx.requester.user_id is not None:
            found = self._directory.resolve_employee_by_user_id(
                tenant_id=tenant_id, user_id=ctx.requester.user_id
            )
            if found is not None:
                return found
        if ctx.requester.employee_resource_id is None:
            return None
        for employee in self._directory.list_employees(tenant_id=tenant_id):
            if employee.resource_id == ctx.requester.employee_resource_id:
                return employee
        return None

    def _sod_for_approval(
        self,
        *,
        tenant_id: UUID,
        requester: EmployeeRecord | None,
        approval_type: str,
        amount: Decimal | None,
        currency: str | None,
        candidate: Any,
    ) -> bool:
        if requester is None:
            return False
        candidate_id = None if candidate is None else getattr(candidate, "employee_id", None)
        if candidate_id is not None:
            sod = self._directory.compare_requester_approver(
                tenant_id=tenant_id,
                requester_employee_id=requester.employee_id,
                approver_employee_id=candidate_id,
            )
            if sod.status == "SAME_PERSON":
                return True
        holders = {
            item.employee_id
            for item in self._directory.resolve_active_approvers(
                tenant_id=tenant_id,
                approval_type=approval_type,
                amount=amount,
                currency=currency,
            )
        }
        if requester.employee_id not in holders:
            return False
        others = holders - {requester.employee_id}
        return candidate_id is None or candidate_id == requester.employee_id or not others

    def _discovery_skills(self, ctx: ProcessContext) -> list[str]:
        skills: list[str] = []
        for activity in ctx.discovery.activities:
            token = (activity.actor or "").strip().lower()
            if token and token not in INVENTED_SKILLS and " " not in token:
                skills.append(token)
        return []  # do not invent; discovery actors are roles, not skills

    async def _allocate(
        self,
        *,
        process_id: UUID,
        tenant_id: UUID,
        requester_user_id: UUID,
        requester_employee_id: UUID | None,
        required_roles: list[str],
        required_department_code: str | None = None,
        skills: list[str] | None = None,
        assignment_kind: str = "allocation",
        required_approval_type: str | None = None,
        minimum_authority_amount: Decimal | None = None,
        authority_currency: str | None = None,
    ) -> dict[str, Any]:
        req = HumanResourceRequirement(
            requester_id=requester_user_id,
            task_deadline=datetime.now(UTC) + timedelta(days=14),
            estimated_effort_hours=Decimal("1"),
            process_stage="RESOURCE_PLANNING",
            process_id=process_id,
            process_context_ref=process_id,
            required_roles=required_roles,
            mandatory_skills=[s for s in (skills or []) if s.lower() not in INVENTED_SKILLS],
            required_department_code=required_department_code,
            assignment_kind=assignment_kind,  # type: ignore[arg-type]
            required_approval_type=required_approval_type,
            minimum_authority_amount=minimum_authority_amount,
            authority_currency=authority_currency,
            requester_employee_id=requester_employee_id,
        )
        request = AllocationRequest(
            metadata=Agent3Metadata(
                correlation_id=uuid4(),
                process_instance_id=process_id,
                task_id=uuid4(),
                tenant_id=tenant_id,
                message_type=Agent3MessageType.RESOURCE_ALLOCATION_REQUEST,
            ),
            human_requirements=req,
            process_context_ref=process_id,
        )
        result = await self._allocator.process_allocation_request(request)
        if result.status.value == "FAILED":
            code = result.error_code or (
                "APPROVER_NOT_RESOLVED"
                if assignment_kind == "approver"
                else "NO_ELIGIBLE_RESOURCE"
            )
            return {"error_code": code, "error_message": result.error_message, "candidate": None}
        human = result.human_requirement_result
        if human is None or not human.eligible_candidates:
            code = human.outcome_code if human is not None else None
            return {
                "error_code": code
                or (
                    "APPROVER_NOT_RESOLVED"
                    if assignment_kind == "approver"
                    else "NO_ELIGIBLE_RESOURCE"
                ),
                "error_message": "No eligible candidate returned by Agent 3",
                "candidate": None,
            }
        return {"candidate": human.eligible_candidates[0], "result": result}

    def _build_step_specs(
        self,
        *,
        ctx: ProcessContext,
        snapshot: PolicyRiskSnapshot | None,
        officer: Any,
        approvers: dict[str, Any],
        issues: list[PlanningIssue],
    ) -> list[CreateWorkflowStepInput]:
        evidence = [
            WorkflowEvidenceRef(evidence_id=item.evidence_id, document_id=item.document_id, kind=item.type)
            for item in ctx.evidence
        ]
        for quote in ctx.quotations:
            if quote.evidence_id:
                evidence.append(
                    WorkflowEvidenceRef(
                        evidence_id=quote.evidence_id,
                        document_id=quote.document_id,
                        kind="quotation",
                    )
                )
        policies = [
            WorkflowPolicyRef(policy_id=str(item), policy_version=ctx.policy.policy_version)
            for item in ctx.policy.policy_ids
        ]
        if snapshot is not None:
            for version in snapshot.policy_versions:
                if not any(ref.policy_version == version for ref in policies):
                    policies.append(
                        WorkflowPolicyRef(
                            policy_id=snapshot.policy_versions[0] if snapshot.policy_versions else "policy",
                            policy_version=version,
                        )
                    )
        context_inputs = {
            "process_id": str(ctx.process_id),
            "amount_ref": "process_context.purchase.amount",
            "currency_ref": "process_context.purchase.currency",
            "vendor_ref": "process_context.purchase.vendor_id",
            "requester_ref": "process_context.requester",
        }
        officer_unresolved = officer is None or officer.employee_id is None
        if officer_unresolved and not any(item.code == "NO_ELIGIBLE_RESOURCE" for item in issues):
            issues.append(
                PlanningIssue(
                    code="NO_ELIGIBLE_RESOURCE",
                    message="Procurement Officer was not resolved",
                    step_key="review-purchase-request",
                )
            )
        specs: list[CreateWorkflowStepInput] = []
        sequence = 1
        specs.append(
            self._step(
                step_key="review-purchase-request",
                sequence=sequence,
                name="Review purchase request",
                description="Review the canonical purchase request in ProcessContext",
                step_type=WorkflowStepType.DOCUMENT_REVIEW,
                employee=officer,
                required_action="REVIEW_PURCHASE_REQUEST",
                required_tool_category="DOCUMENT",
                evidence=evidence,
                policies=policies,
                inputs=context_inputs,
                expected_outputs={"review_status": None},
                unresolved=officer_unresolved,
            )
        )
        sequence += 1
        specs.append(
            self._step(
                step_key="validate-quotations",
                sequence=sequence,
                name="Validate quotation evidence",
                description="Validate quotation evidence referenced by ProcessContext",
                step_type=WorkflowStepType.VALIDATION,
                employee=officer,
                required_action="VALIDATE_QUOTATIONS",
                required_tool_category="VALIDATION",
                depends_on=["review-purchase-request"],
                evidence=evidence,
                policies=policies,
                inputs={**context_inputs, "quotation_count_ref": "process_context.quotations"},
                expected_outputs={"validation_status": None},
                unresolved=officer_unresolved,
            )
        )
        previous = "validate-quotations"
        for approval_type, candidate in approvers.items():
            sequence += 1
            step_key = f"{approval_type.lower().replace('_', '-')}-approval"
            unresolved = candidate is None or candidate.employee_id is None
            specs.append(
                self._step(
                    step_key=step_key,
                    sequence=sequence,
                    name=f"{approval_type.replace('_', ' ').title()} approval",
                    description=f"Human approval required by active policy ({approval_type})",
                    step_type=WorkflowStepType.APPROVAL,
                    employee=candidate,
                    required_action="REQUEST_APPROVAL",
                    required_tool_category="COMMUNICATION",
                    depends_on=[previous],
                    approval_required=True,
                    approval_type=approval_type,
                    evidence=evidence,
                    policies=policies,
                    inputs=context_inputs,
                    expected_outputs={
                        "approval_decision": None,
                        "approver_employee_id": None,
                        "timestamp": None,
                    },
                    unresolved=unresolved,
                    recipients=[] if unresolved else [candidate.employee_id],
                    status=WorkflowStepStatus.WAITING_HUMAN_APPROVAL,
                )
            )
            previous = step_key
        sequence += 1
        specs.append(
            self._step(
                step_key="create-purchase-order",
                sequence=sequence,
                name="Create purchase order",
                description="Create PO after required reviews and approvals. Planning does not execute this.",
                step_type=WorkflowStepType.SYSTEM_ACTION,
                employee=officer,
                required_action="CREATE_PURCHASE_ORDER",
                required_tool_category="PROCUREMENT",
                depends_on=[previous],
                evidence=evidence,
                policies=policies,
                inputs=context_inputs,
                expected_outputs={"purchase_order_id": None, "creation_receipt": None},
                unresolved=officer_unresolved,
            )
        )
        sequence += 1
        specs.append(
            self._step(
                step_key="match-invoice",
                sequence=sequence,
                name="Match invoice",
                description="Deterministically match a persisted invoice to the purchase order. Planning does not execute this.",
                step_type=WorkflowStepType.VALIDATION,
                employee=officer,
                required_action="MATCH_INVOICE",
                required_tool_category="VALIDATION",
                depends_on=["create-purchase-order"],
                evidence=evidence,
                policies=policies,
                inputs=context_inputs,
                expected_outputs={"invoice_match_status": None},
                unresolved=officer_unresolved,
            )
        )
        return specs

    def _step(
        self,
        *,
        step_key: str,
        sequence: int,
        name: str,
        description: str,
        step_type: WorkflowStepType,
        employee: Any,
        required_action: str,
        required_tool_category: str,
        evidence: list[WorkflowEvidenceRef],
        policies: list[WorkflowPolicyRef],
        inputs: dict[str, Any],
        expected_outputs: dict[str, Any],
        unresolved: bool,
        depends_on: list[str] | None = None,
        approval_required: bool = False,
        approval_type: str | None = None,
        recipients: list[UUID] | None = None,
        status: WorkflowStepStatus = WorkflowStepStatus.PENDING,
    ) -> CreateWorkflowStepInput:
        employee_id = None if employee is None else getattr(employee, "employee_id", None)
        resource_id = None if employee is None else getattr(employee, "resource_id", None)
        return CreateWorkflowStepInput(
            step_key=step_key,
            sequence=sequence,
            name=name,
            description=description,
            step_type=step_type,
            status=status,
            responsible_employee_id=None if unresolved else employee_id,
            responsible_resource_id=None if unresolved else resource_id,
            assignment_unresolved=unresolved,
            unresolved_reason="RESPONSIBLE_PERSON_NOT_RESOLVED" if unresolved else None,
            depends_on_step_keys=depends_on or [],
            required_action=required_action,
            required_tool_category=required_tool_category,
            inputs=dict(inputs),
            expected_outputs=dict(expected_outputs),
            evidence_refs=list(evidence),
            policy_refs=list(policies),
            approval_required=approval_required,
            approval_type=approval_type,
            recipient_employee_ids=recipients or [],
        )

    async def _attach_tool_resolution(
        self,
        tenant_id: UUID,
        spec: CreateWorkflowStepInput,
        issues: list[PlanningIssue],
    ) -> None:
        step_like = spec
        try:
            resolved = await self._tools.resolve_for_step(tenant_id=tenant_id, workflow_step=step_like)
            spec.inputs["tool_resolution"] = {
                "status": "RESOLVED",
                "tool_name": resolved.tool_name,
                "implementation_key": resolved.implementation_key,
                "agent2_tool_name": resolved.agent2_tool_name,
            }
        except ToolNotRegisteredError as exc:
            spec.inputs["tool_resolution"] = {"status": "TOOL_NOT_REGISTERED"}
            issues.append(
                PlanningIssue(
                    code="TOOL_NOT_REGISTERED",
                    message=str(exc),
                    blocking=False,
                    step_key=spec.step_key,
                )
            )
        except ToolDisabledError as exc:
            spec.inputs["tool_resolution"] = {"status": "TOOL_DISABLED"}
            issues.append(
                PlanningIssue(code="TOOL_DISABLED", message=str(exc), blocking=True, step_key=spec.step_key)
            )
        except ToolAmbiguousError as exc:
            spec.inputs["tool_resolution"] = {"status": "TOOL_AMBIGUOUS"}
            issues.append(
                PlanningIssue(code="TOOL_AMBIGUOUS", message=str(exc), blocking=True, step_key=spec.step_key)
            )
        except ToolCategoryMismatchError as exc:
            spec.inputs["tool_resolution"] = {"status": "TOOL_CATEGORY_MISMATCH"}
            issues.append(
                PlanningIssue(
                    code="TOOL_CATEGORY_MISMATCH",
                    message=str(exc),
                    blocking=True,
                    step_key=spec.step_key,
                )
            )
        except ToolStepTypeNotAllowedError as exc:
            spec.inputs["tool_resolution"] = {"status": "TOOL_STEP_TYPE_NOT_ALLOWED"}
            issues.append(
                PlanningIssue(
                    code="TOOL_STEP_TYPE_NOT_ALLOWED",
                    message=str(exc),
                    blocking=True,
                    step_key=spec.step_key,
                )
            )

    async def _ensure_plan_process(
        self, process_id: UUID, tenant_id: UUID, ctx: ProcessContext
    ) -> None:
        binding = await self._plans._repo.get_process_binding(process_id)  # noqa: SLF001
        if binding is None:
            await self._plans._repo.register_process(  # noqa: SLF001
                process_id,
                tenant_id,
                process_context_schema_version=ctx.schema_version,
            )

    async def _persist_failed_draft(
        self,
        process_id: UUID,
        tenant_id: UUID,
        ctx: ProcessContext,
        issues: list[PlanningIssue],
        snapshot: PolicyRiskSnapshot | None,
    ) -> WorkflowPlanningResult:
        await self._ensure_plan_process(process_id, tenant_id, ctx)
        draft = await self._plans.create_draft(
            CreateWorkflowPlanInput(
                process_id=process_id,
                source_process_context_schema_version=ctx.schema_version,
            ),
            tenant_id=tenant_id,
        )
        _ = snapshot
        return WorkflowPlanningResult(
            process_id=process_id,
            tenant_id=tenant_id,
            workflow_plan_id=draft.id,
            version=draft.version,
            status=draft.status.value,
            execution_ready=False,
            structurally_valid=False,
            issues=issues,
            plan=draft,
        )
