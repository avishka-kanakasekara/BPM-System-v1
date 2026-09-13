"""Typed company directory records. Emails and IDs are never guessed."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EmployeeStatus = Literal["active", "inactive"]
DepartmentStatus = Literal["active", "inactive"]
SodStatus = Literal["SAME_PERSON", "DISTINCT", "APPROVER_NOT_RESOLVED"]


class DepartmentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department_id: UUID
    tenant_id: UUID
    name: str
    code: str
    manager_employee_id: UUID | None = None
    status: DepartmentStatus = "active"


class RoleRecord(BaseModel):
    """Company job role — stored as tenant data, not app constants."""

    model_config = ConfigDict(extra="forbid")

    role_id: UUID
    tenant_id: UUID
    name: str
    code: str
    description: str | None = None
    department_id: UUID | None = None
    status: EmployeeStatus = "active"


class EmployeeRecord(BaseModel):
    """Company employee. Distinct from JWT user_id and Agent 3 resource_id."""

    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    tenant_id: UUID
    employee_number: str
    full_name: str
    email: str
    phone: str | None = None
    department_id: UUID
    role_id: UUID
    manager_employee_id: UUID | None = None
    status: EmployeeStatus = "active"
    resource_id: UUID | None = None
    user_id: UUID | None = None
    skill_codes: list[str] = Field(default_factory=list)
    is_available: bool = True
    current_workload_pct: Decimal | None = None
    max_workload_pct: Decimal | None = None

    @field_validator("email")
    @classmethod
    def _email_required(cls, value: str) -> str:
        text = (value or "").strip()
        if not text or "@" not in text:
            raise ValueError("employee email must be a verified company address")
        return text.lower()

    @model_validator(mode="after")
    def _no_self_manager(self) -> EmployeeRecord:
        if self.manager_employee_id is not None and self.manager_employee_id == self.employee_id:
            raise ValueError("employee cannot manage themselves")
        return self


class ApprovalAuthorityRecord(BaseModel):
    """Who is authorized to approve. Policy still decides when approval is required."""

    model_config = ConfigDict(extra="forbid")

    authority_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    employee_id: UUID | None = None
    role_id: UUID | None = None
    department_id: UUID | None = None
    approval_type: str
    authority_code: str | None = None
    max_amount: Decimal
    currency: str
    is_active: bool = True

    @model_validator(mode="after")
    def _subject_present(self) -> ApprovalAuthorityRecord:
        if self.employee_id is None and self.role_id is None:
            raise ValueError("approval authority requires employee_id or role_id")
        return self


class IdentityMapping(BaseModel):
    """Auth user, company employee, and Agent 3 resource — three distinct IDs."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    auth_user_id: UUID
    employee_id: UUID | None = None
    resource_id: UUID | None = None


class ApproverCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    employee_number: str
    full_name: str
    email: str
    role_name: str
    role_code: str
    department_code: str | None = None
    authority_code: str | None = None
    approval_type: str
    max_amount: Decimal
    currency: str
    resource_id: UUID | None = None


class SodComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: SodStatus
    requester_employee_id: UUID | None = None
    approver_employee_id: UUID | None = None
    same_person: bool = False


class CreateEmployeeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    employee_number: str
    full_name: str
    email: str
    department_id: UUID
    role_id: UUID
    employee_id: UUID | None = None
    phone: str | None = None
    manager_employee_id: UUID | None = None
    status: EmployeeStatus = "active"
    resource_id: UUID | None = None
    user_id: UUID | None = None
    skill_codes: list[str] = Field(default_factory=list)
    is_available: bool = True
    current_workload_pct: Decimal | None = None
    max_workload_pct: Decimal | None = None


class BudgetDepartmentLink(BaseModel):
    """Ownership context for an existing Agent 3 budget resource."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    resource_id: UUID
    department_id: UUID
    linked_at: datetime | None = None
