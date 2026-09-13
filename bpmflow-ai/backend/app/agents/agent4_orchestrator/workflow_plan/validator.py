"""Deterministic WorkflowPlan structural validation. No LLM."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol
from uuid import UUID

from app.company_directory.schemas import EmployeeRecord
from app.company_directory.service import CompanyDirectoryService

from .constants import (
    HUMAN_STEP_TYPES,
    TOOL_CATEGORY_REQUIRED_TYPES,
    WorkflowStepType,
)
from .schemas import (
    UNRESOLVED_RESPONSIBLE_PERSON,
    ValidationIssue,
    WorkflowEvidenceRef,
    WorkflowPlanRecord,
    WorkflowPlanValidationResult,
    WorkflowPolicyRef,
    WorkflowStepRecord,
)


class ProcessBinding(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def tenant_id(self) -> UUID | None: ...


class WorkflowPlanValidator:
    """Structural correctness for Agent 4 plans. Never invents people or facts."""

    def __init__(self, directory: CompanyDirectoryService | None = None) -> None:
        self._directory = directory

    def validate(
        self,
        plan: WorkflowPlanRecord,
        *,
        process: ProcessBinding | None = None,
    ) -> WorkflowPlanValidationResult:
        issues: list[ValidationIssue] = []
        issues.extend(self._plan_identity(plan, process))
        issues.extend(self._version(plan))
        if not plan.steps:
            issues.append(
                ValidationIssue(
                    code="EMPTY_PLAN",
                    message="Workflow plan must contain at least one step before activation",
                )
            )
        issues.extend(self._sequences_and_keys(plan))
        issues.extend(self._dependencies(plan))
        for step in plan.steps:
            issues.extend(self._step_requirements(plan, step))
            issues.extend(self._assignment(plan, step))
            issues.extend(self._recipients(plan, step))
            issues.extend(self._refs(step))
        return WorkflowPlanValidationResult(valid=not issues, issues=issues)

    def _plan_identity(
        self, plan: WorkflowPlanRecord, process: ProcessBinding | None
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if process is None:
            issues.append(
                ValidationIssue(
                    code="PROCESS_NOT_BOUND",
                    message="Workflow plan must reference a known process",
                )
            )
            return issues
        if process.id != plan.process_id:
            issues.append(
                ValidationIssue(
                    code="PLAN_PROCESS_MISMATCH",
                    message="Workflow plan process_id does not match the bound process",
                )
            )
        if process.tenant_id is None or process.tenant_id != plan.tenant_id:
            issues.append(
                ValidationIssue(
                    code="CROSS_TENANT_DENIED",
                    message="Workflow plan and process must belong to the same tenant",
                )
            )
        return issues

    def _version(self, plan: WorkflowPlanRecord) -> list[ValidationIssue]:
        if plan.version < 1:
            return [
                ValidationIssue(
                    code="INVALID_VERSION",
                    message="Workflow plan version must be >= 1",
                )
            ]
        return []

    def _sequences_and_keys(self, plan: WorkflowPlanRecord) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        keys: dict[str, int] = {}
        sequences: dict[int, str] = {}
        for step in plan.steps:
            if step.tenant_id != plan.tenant_id:
                issues.append(
                    ValidationIssue(
                        code="CROSS_TENANT_DENIED",
                        message="Workflow step tenant does not match plan tenant",
                        step_key=step.step_key,
                    )
                )
            if step.workflow_plan_id != plan.id:
                issues.append(
                    ValidationIssue(
                        code="PLAN_PROCESS_MISMATCH",
                        message="Workflow step does not belong to this plan",
                        step_key=step.step_key,
                    )
                )
            if step.step_key in keys:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_STEP_KEY",
                        message=f"Duplicate step_key '{step.step_key}'",
                        step_key=step.step_key,
                    )
                )
            keys[step.step_key] = step.sequence
            if step.sequence in sequences:
                issues.append(
                    ValidationIssue(
                        code="INVALID_SEQUENCE",
                        message=f"Duplicate sequence {step.sequence}",
                        step_key=step.step_key,
                    )
                )
            sequences[step.sequence] = step.step_key
            if step.sequence < 1:
                issues.append(
                    ValidationIssue(
                        code="INVALID_SEQUENCE",
                        message="Sequence numbers must be >= 1",
                        step_key=step.step_key,
                    )
                )
        return issues

    def _dependencies(self, plan: WorkflowPlanRecord) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        keys = {step.step_key for step in plan.steps}
        graph: dict[str, list[str]] = defaultdict(list)
        seen_edges: set[tuple[str, str]] = set()
        for step in plan.steps:
            for dep in step.depends_on_step_keys:
                if dep == step.step_key:
                    issues.append(
                        ValidationIssue(
                            code="SELF_DEPENDENCY",
                            message="A step cannot depend on itself",
                            step_key=step.step_key,
                        )
                    )
                    continue
                if dep not in keys:
                    issues.append(
                        ValidationIssue(
                            code="DEPENDENCY_NOT_FOUND",
                            message=f"Dependency '{dep}' is not in this workflow plan",
                            step_key=step.step_key,
                        )
                    )
                    continue
                edge = (step.step_key, dep)
                if edge in seen_edges:
                    issues.append(
                        ValidationIssue(
                            code="DUPLICATE_DEPENDENCY",
                            message=f"Duplicate dependency on '{dep}'",
                            step_key=step.step_key,
                        )
                    )
                    continue
                seen_edges.add(edge)
                graph[step.step_key].append(dep)
        cycle = self._find_cycle(keys, graph)
        if cycle is not None:
            issues.append(
                ValidationIssue(
                    code="DEPENDENCY_CYCLE",
                    message=f"Dependency cycle: {' -> '.join(cycle)}",
                    step_key=cycle[0],
                )
            )
        return issues

    def _find_cycle(self, keys: set[str], graph: dict[str, list[str]]) -> list[str] | None:
        visiting: set[str] = set()
        visited: set[str] = set()
        stack: list[str] = []

        def dfs(node: str) -> list[str] | None:
            visiting.add(node)
            stack.append(node)
            for nxt in graph.get(node, []):
                if nxt in visiting:
                    start = stack.index(nxt)
                    return stack[start:] + [nxt]
                if nxt not in visited:
                    found = dfs(nxt)
                    if found is not None:
                        return found
            visiting.remove(node)
            stack.pop()
            visited.add(node)
            return None

        for key in keys:
            if key not in visited:
                found = dfs(key)
                if found is not None:
                    return found
        return None

    def _step_requirements(
        self, plan: WorkflowPlanRecord, step: WorkflowStepRecord
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not (step.required_action or "").strip():
            issues.append(
                ValidationIssue(
                    code="REQUIRED_ACTION_MISSING",
                    message="required_action must be declared",
                    step_key=step.step_key,
                )
            )
        if step.step_type in TOOL_CATEGORY_REQUIRED_TYPES and not (
            step.required_tool_category or ""
        ).strip():
            issues.append(
                ValidationIssue(
                    code="REQUIRED_TOOL_CATEGORY_MISSING",
                    message="required_tool_category must be declared for this step type",
                    step_key=step.step_key,
                )
            )
        if step.step_type == WorkflowStepType.APPROVAL or step.approval_required:
            if not step.approval_required:
                issues.append(
                    ValidationIssue(
                        code="APPROVAL_METADATA_MISSING",
                        message="APPROVAL steps must set approval_required",
                        step_key=step.step_key,
                    )
                )
            if not (step.approval_type or "").strip():
                issues.append(
                    ValidationIssue(
                        code="APPROVAL_METADATA_MISSING",
                        message="Approval steps require approval_type",
                        step_key=step.step_key,
                    )
                )
        if step.step_type == WorkflowStepType.COMMUNICATION and not step.recipient_employee_ids:
            issues.append(
                ValidationIssue(
                    code="RECIPIENT_REQUIRED",
                    message="COMMUNICATION steps require recipient_employee_ids",
                    step_key=step.step_key,
                )
            )
        return issues

    def _assignment(
        self, plan: WorkflowPlanRecord, step: WorkflowStepRecord
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        needs_human = step.step_type in HUMAN_STEP_TYPES
        if step.assignment_unresolved or (
            needs_human and step.responsible_employee_id is None
        ):
            reason = step.unresolved_reason or UNRESOLVED_RESPONSIBLE_PERSON
            issues.append(
                ValidationIssue(
                    code=UNRESOLVED_RESPONSIBLE_PERSON,
                    message=reason,
                    step_key=step.step_key,
                )
            )
            return issues
        if self._directory is None:
            return issues
        employee = self._employee(plan.tenant_id, step.responsible_employee_id)
        if step.responsible_employee_id is not None and employee is None:
            issues.append(
                ValidationIssue(
                    code="CROSS_TENANT_DENIED",
                    message="responsible_employee_id is not in this tenant",
                    step_key=step.step_key,
                )
            )
            return issues
        if employee is not None:
            issues.extend(self._employee_context(plan.tenant_id, step, employee))
        elif step.responsible_resource_id is not None:
            mapped = self._directory.resolve_employee_by_employee_id(
                tenant_id=plan.tenant_id, employee_id=step.responsible_resource_id
            )
            # resource_id is not employee_id; look up via employees' resource_id
            if not self._resource_in_tenant(plan.tenant_id, step.responsible_resource_id):
                issues.append(
                    ValidationIssue(
                        code="CROSS_TENANT_DENIED",
                        message="responsible_resource_id is not in this tenant",
                        step_key=step.step_key,
                    )
                )
            _ = mapped
        if step.responsible_role_id is not None:
            role = self._directory.get_role(
                tenant_id=plan.tenant_id, role_id=step.responsible_role_id
            )
            if role is None:
                issues.append(
                    ValidationIssue(
                        code="CROSS_TENANT_DENIED",
                        message="responsible_role_id is not in this tenant",
                        step_key=step.step_key,
                    )
                )
        if step.responsible_department_id is not None:
            dept = self._directory.get_department(
                tenant_id=plan.tenant_id, department_id=step.responsible_department_id
            )
            if dept is None:
                issues.append(
                    ValidationIssue(
                        code="CROSS_TENANT_DENIED",
                        message="responsible_department_id is not in this tenant",
                        step_key=step.step_key,
                    )
                )
        return issues

    def _employee_context(
        self,
        tenant_id: UUID,
        step: WorkflowStepRecord,
        employee: EmployeeRecord,
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if employee.tenant_id != tenant_id:
            issues.append(
                ValidationIssue(
                    code="CROSS_TENANT_DENIED",
                    message="responsible employee belongs to another tenant",
                    step_key=step.step_key,
                )
            )
        if (
            step.responsible_resource_id is not None
            and employee.resource_id is not None
            and step.responsible_resource_id != employee.resource_id
        ):
            issues.append(
                ValidationIssue(
                    code="EMPLOYEE_RESOURCE_MISMATCH",
                    message="responsible_resource_id does not match the employee's resource",
                    step_key=step.step_key,
                )
            )
        if (
            step.responsible_resource_id is not None
            and employee.resource_id is None
        ):
            issues.append(
                ValidationIssue(
                    code="EMPLOYEE_RESOURCE_MISMATCH",
                    message="employee has no resource mapping for the provided resource_id",
                    step_key=step.step_key,
                )
            )
        if (
            step.responsible_role_id is not None
            and step.responsible_role_id != employee.role_id
        ):
            issues.append(
                ValidationIssue(
                    code="EMPLOYEE_RESOURCE_MISMATCH",
                    message="responsible_role_id does not match the employee's role",
                    step_key=step.step_key,
                )
            )
        if (
            step.responsible_department_id is not None
            and step.responsible_department_id != employee.department_id
        ):
            issues.append(
                ValidationIssue(
                    code="EMPLOYEE_RESOURCE_MISMATCH",
                    message="responsible_department_id does not match the employee's department",
                    step_key=step.step_key,
                )
            )
        return issues

    def _resource_in_tenant(self, tenant_id: UUID, resource_id: UUID) -> bool:
        if self._directory is None:
            return False
        for employee in self._directory.list_employees(tenant_id=tenant_id):
            if employee.resource_id == resource_id:
                return True
        return False

    def _recipients(
        self, plan: WorkflowPlanRecord, step: WorkflowStepRecord
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if self._directory is None:
            return issues
        for recipient_id in step.recipient_employee_ids:
            employee = self._employee(plan.tenant_id, recipient_id)
            if employee is None:
                issues.append(
                    ValidationIssue(
                        code="CROSS_TENANT_DENIED",
                        message="recipient_employee_id is not in this tenant",
                        step_key=step.step_key,
                    )
                )
        return issues

    def _refs(self, step: WorkflowStepRecord) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for item in step.evidence_refs:
            if not isinstance(item, WorkflowEvidenceRef) or not item.evidence_id.strip():
                issues.append(
                    ValidationIssue(
                        code="INVALID_EVIDENCE_REF",
                        message="evidence_refs must include a non-empty evidence_id",
                        step_key=step.step_key,
                    )
                )
        for item in step.policy_refs:
            if not isinstance(item, WorkflowPolicyRef) or not item.policy_id.strip():
                issues.append(
                    ValidationIssue(
                        code="INVALID_POLICY_REF",
                        message="policy_refs must include a non-empty policy_id",
                        step_key=step.step_key,
                    )
                )
        return issues

    def _employee(self, tenant_id: UUID, employee_id: UUID | None) -> EmployeeRecord | None:
        if employee_id is None or self._directory is None:
            return None
        return self._directory.resolve_employee_by_employee_id(
            tenant_id=tenant_id, employee_id=employee_id
        )
