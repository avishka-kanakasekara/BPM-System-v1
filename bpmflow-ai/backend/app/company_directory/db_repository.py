"""Tenant-scoped Company Directory persistence (SQLAlchemy + PostgREST).

Does not cache employee records. Does not fall back to demo data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.logging import get_logger
from app.core.supabase_rest import rest_insert, rest_select

from .exceptions import (
    CompanyDirectoryUnavailableError,
    CrossTenantDirectoryError,
    InvalidManagerError,
)
from .schemas import (
    ApprovalAuthorityRecord,
    BudgetDepartmentLink,
    CreateEmployeeInput,
    DepartmentRecord,
    EmployeeRecord,
    IdentityMapping,
    RoleRecord,
)

logger = get_logger(__name__)


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _as_uuid_opt(value: Any) -> UUID | None:
    if value in (None, ""):
        return None
    return _as_uuid(value)


def _as_decimal_opt(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _bind(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _params(values: dict[str, Any]) -> dict[str, Any]:
    return {key: _bind(value) for key, value in values.items()}
    return CompanyDirectoryUnavailableError(
        "Company directory database is unavailable",
        error_code="COMPANY_DIRECTORY_UNAVAILABLE",
    )


class SqlAlchemyCompanyDirectoryRepository:
    """Postgres-backed directory. Every query includes tenant_id."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _exec(self, session: Session, statement, params: dict[str, Any]):
        return session.execute(statement, _params(params))

    def clear(self) -> None:
        return None

    def _session(self) -> Session:
        return self._session_factory()

    def create_department(self, department: DepartmentRecord) -> DepartmentRecord:
        try:
            with self._session() as session:
                self._exec(session, 
                    text(
                        """
                        INSERT INTO departments (id, tenant_id, name, code, manager_employee_id, status)
                        VALUES (:id, :tenant_id, :name, :code, :manager_employee_id, :status)
                        """
                    ),
                    {
                        "id": department.department_id,
                        "tenant_id": department.tenant_id,
                        "name": department.name,
                        "code": department.code,
                        "manager_employee_id": department.manager_employee_id,
                        "status": department.status,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return department

    def create_role(self, role: RoleRecord) -> RoleRecord:
        try:
            with self._session() as session:
                self._exec(session, 
                    text(
                        """
                        INSERT INTO roles (id, tenant_id, code, name, description, department_id, status)
                        VALUES (:id, :tenant_id, :code, :name, :description, :department_id, :status)
                        """
                    ),
                    {
                        "id": role.role_id,
                        "tenant_id": role.tenant_id,
                        "code": role.code,
                        "name": role.name,
                        "description": role.description,
                        "department_id": role.department_id,
                        "status": role.status,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return role

    def create_employee(self, payload: CreateEmployeeInput) -> EmployeeRecord:
        if self.get_department(tenant_id=payload.tenant_id, department_id=payload.department_id) is None:
            raise InvalidManagerError("department not found in tenant", error_code="DEPARTMENT_NOT_FOUND")
        if self.get_role(tenant_id=payload.tenant_id, role_id=payload.role_id) is None:
            raise InvalidManagerError("role not found in tenant", error_code="ROLE_NOT_FOUND")
        employee_id = payload.employee_id or uuid4()
        manager_id = payload.manager_employee_id
        if manager_id is not None:
            if manager_id == employee_id:
                raise InvalidManagerError("employee cannot manage themselves")
            manager = self.get_employee(tenant_id=payload.tenant_id, employee_id=manager_id)
            if manager is None:
                raise InvalidManagerError("manager must belong to the same tenant")
        try:
            with self._session() as session:
                self._exec(session, 
                    text(
                        """
                        INSERT INTO employees (
                            id, tenant_id, employee_number, full_name, email, phone,
                            department_id, role_id, manager_employee_id, status, resource_id
                        ) VALUES (
                            :id, :tenant_id, :employee_number, :full_name, :email, :phone,
                            :department_id, :role_id, :manager_employee_id, :status, :resource_id
                        )
                        """
                    ),
                    {
                        "id": employee_id,
                        "tenant_id": payload.tenant_id,
                        "employee_number": payload.employee_number,
                        "full_name": payload.full_name,
                        "email": payload.email.strip().lower(),
                        "phone": payload.phone,
                        "department_id": payload.department_id,
                        "role_id": payload.role_id,
                        "manager_employee_id": manager_id,
                        "status": payload.status,
                        "resource_id": payload.resource_id,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        if payload.user_id is not None:
            self.link_identity(
                IdentityMapping(
                    tenant_id=payload.tenant_id,
                    auth_user_id=payload.user_id,
                    employee_id=employee_id,
                    resource_id=payload.resource_id,
                )
            )
        self._persist_employee_profile(payload, employee_id)
        stored = self.get_employee(tenant_id=payload.tenant_id, employee_id=employee_id)
        if stored is None:
            raise _unavailable(RuntimeError("employee insert did not round-trip"))
        return stored.model_copy(
            update={
                "skill_codes": stored.skill_codes or list(payload.skill_codes),
                "is_available": payload.is_available if stored.resource_id is None else stored.is_available,
                "current_workload_pct": payload.current_workload_pct
                if stored.current_workload_pct is None
                else stored.current_workload_pct,
                "max_workload_pct": payload.max_workload_pct
                if stored.max_workload_pct is None
                else stored.max_workload_pct,
            }
        )

    def create_authority(self, authority: ApprovalAuthorityRecord) -> ApprovalAuthorityRecord:
        try:
            with self._session() as session:
                self._exec(session, 
                    text(
                        """
                        INSERT INTO approval_authorities (
                            id, tenant_id, employee_id, role_id, department_id,
                            approval_type, authority_code, max_amount, currency, is_active
                        ) VALUES (
                            :id, :tenant_id, :employee_id, :role_id, :department_id,
                            :approval_type, :authority_code, :max_amount, :currency, :is_active
                        )
                        """
                    ),
                    {
                        "id": authority.authority_id,
                        "tenant_id": authority.tenant_id,
                        "employee_id": authority.employee_id,
                        "role_id": authority.role_id,
                        "department_id": authority.department_id,
                        "approval_type": authority.approval_type,
                        "authority_code": authority.authority_code,
                        "max_amount": authority.max_amount,
                        "currency": authority.currency,
                        "is_active": authority.is_active,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return authority

    def link_identity(self, mapping: IdentityMapping) -> IdentityMapping:
        try:
            with self._session() as session:
                self._exec(session, 
                    text(
                        """
                        INSERT INTO identity_links (
                            tenant_id, user_id, employee_id, resource_id, employee_resource_id
                        ) VALUES (
                            :tenant_id, :user_id, :employee_id, :resource_id, :employee_resource_id
                        )
                        ON CONFLICT (tenant_id, user_id) DO UPDATE SET
                            employee_id = EXCLUDED.employee_id,
                            resource_id = EXCLUDED.resource_id,
                            employee_resource_id = EXCLUDED.employee_resource_id
                        """
                    ),
                    {
                        "tenant_id": mapping.tenant_id,
                        "user_id": mapping.auth_user_id,
                        "employee_id": mapping.employee_id,
                        "resource_id": mapping.resource_id,
                        "employee_resource_id": mapping.resource_id,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return mapping

    def link_budget_department(self, link: BudgetDepartmentLink) -> BudgetDepartmentLink:
        if self.get_department(tenant_id=link.tenant_id, department_id=link.department_id) is None:
            raise InvalidManagerError("department not found in tenant", error_code="DEPARTMENT_NOT_FOUND")
        try:
            with self._session() as session:
                self._exec(session, 
                    text(
                        """
                        UPDATE budget_resource_profiles
                        SET department_id = :department_id
                        WHERE tenant_id = :tenant_id AND resource_id = :resource_id
                        """
                    ),
                    {
                        "department_id": link.department_id,
                        "tenant_id": link.tenant_id,
                        "resource_id": link.resource_id,
                    },
                )
                session.commit()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return link

    def get_employee(self, *, tenant_id: UUID, employee_id: UUID) -> EmployeeRecord | None:
        try:
            with self._session() as session:
                row = self._exec(session, 
                    text(
                        """
                        SELECT e.id, e.tenant_id, e.employee_number, e.full_name, e.email, e.phone,
                               e.department_id, e.role_id, e.manager_employee_id, e.status, e.resource_id,
                               il.user_id AS user_id
                        FROM employees e
                        LEFT JOIN identity_links il
                          ON il.tenant_id = e.tenant_id AND il.employee_id = e.id
                        WHERE e.tenant_id = :tenant_id AND e.id = :employee_id
                        """
                    ),
                    {"tenant_id": tenant_id, "employee_id": employee_id},
                ).mappings().first()
                if row is None:
                    return None
                if _as_uuid(row["tenant_id"]) != tenant_id:
                    raise CrossTenantDirectoryError("tenant A cannot resolve tenant B directory data")
                skills = self._skill_codes(session, tenant_id, _as_uuid_opt(row["resource_id"]))
                availability = self._availability(session, tenant_id, _as_uuid_opt(row["resource_id"]))
                workload = self._workload(session, tenant_id, _as_uuid_opt(row["resource_id"]))
        except CrossTenantDirectoryError:
            raise
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return self._employee_from_row(row, skills, availability, workload)

    def get_department(self, *, tenant_id: UUID, department_id: UUID) -> DepartmentRecord | None:
        try:
            with self._session() as session:
                row = self._exec(session, 
                    text(
                        """
                        SELECT id, tenant_id, name, code, manager_employee_id, status
                        FROM departments
                        WHERE tenant_id = :tenant_id AND id = :department_id
                        """
                    ),
                    {"tenant_id": tenant_id, "department_id": department_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        if row is None:
            return None
        return DepartmentRecord(
            department_id=_as_uuid(row["id"]),
            tenant_id=_as_uuid(row["tenant_id"]),
            name=row["name"],
            code=row["code"],
            manager_employee_id=_as_uuid_opt(row["manager_employee_id"]),
            status=row["status"],
        )

    def get_role(self, *, tenant_id: UUID, role_id: UUID) -> RoleRecord | None:
        try:
            with self._session() as session:
                row = self._exec(session, 
                    text(
                        """
                        SELECT id, tenant_id, name, code, description, department_id, status
                        FROM roles
                        WHERE tenant_id = :tenant_id AND id = :role_id
                        """
                    ),
                    {"tenant_id": tenant_id, "role_id": role_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        if row is None:
            return None
        return RoleRecord(
            role_id=_as_uuid(row["id"]),
            tenant_id=_as_uuid(row["tenant_id"]),
            name=row["name"],
            code=row["code"],
            description=row.get("description"),
            department_id=_as_uuid_opt(row.get("department_id")),
            status=row.get("status") or "active",
        )

    def list_employees(self, *, tenant_id: UUID) -> list[EmployeeRecord]:
        try:
            with self._session() as session:
                rows = self._exec(session, 
                    text(
                        """
                        SELECT e.id, e.tenant_id, e.employee_number, e.full_name, e.email, e.phone,
                               e.department_id, e.role_id, e.manager_employee_id, e.status, e.resource_id,
                               il.user_id AS user_id
                        FROM employees e
                        LEFT JOIN identity_links il
                          ON il.tenant_id = e.tenant_id AND il.employee_id = e.id
                        WHERE e.tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().all()
                results: list[EmployeeRecord] = []
                for row in rows:
                    resource_id = _as_uuid_opt(row["resource_id"])
                    results.append(
                        self._employee_from_row(
                            row,
                            self._skill_codes(session, tenant_id, resource_id),
                            self._availability(session, tenant_id, resource_id),
                            self._workload(session, tenant_id, resource_id),
                        )
                    )
                return results
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc

    def list_departments(self, *, tenant_id: UUID) -> list[DepartmentRecord]:
        try:
            with self._session() as session:
                rows = self._exec(session, 
                    text(
                        """
                        SELECT id, tenant_id, name, code, manager_employee_id, status
                        FROM departments WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return [
            DepartmentRecord(
                department_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                name=row["name"],
                code=row["code"],
                manager_employee_id=_as_uuid_opt(row["manager_employee_id"]),
                status=row["status"],
            )
            for row in rows
        ]

    def list_roles(self, *, tenant_id: UUID) -> list[RoleRecord]:
        try:
            with self._session() as session:
                rows = self._exec(session, 
                    text(
                        """
                        SELECT id, tenant_id, name, code, description, department_id, status
                        FROM roles WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return [
            RoleRecord(
                role_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                name=row["name"],
                code=row["code"],
                description=row.get("description"),
                department_id=_as_uuid_opt(row.get("department_id")),
                status=row.get("status") or "active",
            )
            for row in rows
        ]

    def list_authorities(self, *, tenant_id: UUID) -> list[ApprovalAuthorityRecord]:
        try:
            with self._session() as session:
                rows = self._exec(session, 
                    text(
                        """
                        SELECT id, tenant_id, employee_id, role_id, department_id,
                               approval_type, authority_code, max_amount, currency, is_active
                        FROM approval_authorities WHERE tenant_id = :tenant_id
                        """
                    ),
                    {"tenant_id": tenant_id},
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        return [
            ApprovalAuthorityRecord(
                authority_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                employee_id=_as_uuid_opt(row["employee_id"]),
                role_id=_as_uuid_opt(row["role_id"]),
                department_id=_as_uuid_opt(row["department_id"]),
                approval_type=row["approval_type"],
                authority_code=row["authority_code"],
                max_amount=Decimal(str(row["max_amount"])),
                currency=row["currency"],
                is_active=bool(row["is_active"]),
            )
            for row in rows
        ]

    def get_identity_by_user(self, *, tenant_id: UUID, user_id: UUID) -> IdentityMapping | None:
        try:
            with self._session() as session:
                row = self._exec(session, 
                    text(
                        """
                        SELECT tenant_id, user_id, employee_id, resource_id
                        FROM identity_links
                        WHERE tenant_id = :tenant_id AND user_id = :user_id
                        """
                    ),
                    {"tenant_id": tenant_id, "user_id": user_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        if row is None:
            return None
        return IdentityMapping(
            tenant_id=_as_uuid(row["tenant_id"]),
            auth_user_id=_as_uuid(row["user_id"]),
            employee_id=_as_uuid_opt(row["employee_id"]),
            resource_id=_as_uuid_opt(row["resource_id"]),
        )

    def get_identity_by_employee(self, *, tenant_id: UUID, employee_id: UUID) -> IdentityMapping | None:
        try:
            with self._session() as session:
                row = self._exec(session, 
                    text(
                        """
                        SELECT tenant_id, user_id, employee_id, resource_id
                        FROM identity_links
                        WHERE tenant_id = :tenant_id AND employee_id = :employee_id
                        """
                    ),
                    {"tenant_id": tenant_id, "employee_id": employee_id},
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise _unavailable(exc) from exc
        if row is None:
            return None
        return IdentityMapping(
            tenant_id=_as_uuid(row["tenant_id"]),
            auth_user_id=_as_uuid(row["user_id"]),
            employee_id=_as_uuid_opt(row["employee_id"]),
            resource_id=_as_uuid_opt(row["resource_id"]),
        )

    def get_budget_link(self, *, tenant_id: UUID, resource_id: UUID) -> BudgetDepartmentLink | None:
        try:
            with self._session() as session:
                row = self._exec(session, 
                    text(
                        """
                        SELECT tenant_id, resource_id, department_id
                        FROM budget_resource_profiles
                        WHERE tenant_id = :tenant_id AND resource_id = :resource_id
                        """
                    ),
                    {"tenant_id": tenant_id, "resource_id": resource_id},
                ).mappings().first()
        except SQLAlchemyError:
            return None
        if row is None or row.get("department_id") in (None, ""):
            return None
        return BudgetDepartmentLink(
            tenant_id=_as_uuid(row["tenant_id"]),
            resource_id=_as_uuid(row["resource_id"]),
            department_id=_as_uuid(row["department_id"]),
        )

    def _skill_codes(self, session: Session, tenant_id: UUID, resource_id: UUID | None) -> list[str]:
        if resource_id is None:
            return []
        try:
            rows = self._exec(session, 
                text(
                    """
                    SELECT s.code
                    FROM resource_skills rs
                    JOIN skills s ON s.tenant_id = rs.tenant_id AND s.id = rs.skill_id
                    WHERE rs.tenant_id = :tenant_id AND rs.resource_id = :resource_id
                    """
                ),
                {"tenant_id": tenant_id, "resource_id": resource_id},
            ).mappings().all()
        except SQLAlchemyError:
            return []
        return [str(row["code"]) for row in rows if row.get("code")]

    def _availability(
        self, session: Session, tenant_id: UUID, resource_id: UUID | None
    ) -> bool | None:
        if resource_id is None:
            return None
        try:
            row = self._exec(session, 
                text(
                    """
                    SELECT 1 AS present
                    FROM resource_availability
                    WHERE tenant_id = :tenant_id AND resource_id = :resource_id
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "resource_id": resource_id},
            ).first()
        except SQLAlchemyError:
            return None
        return True if row is not None else False

    def _workload(
        self, session: Session, tenant_id: UUID, resource_id: UUID | None
    ) -> tuple[Decimal | None, Decimal | None]:
        if resource_id is None:
            return (None, None)
        try:
            row = self._exec(session, 
                text(
                    """
                    SELECT current_workload_pct, max_workload_pct
                    FROM workload_snapshots
                    WHERE tenant_id = :tenant_id AND resource_id = :resource_id
                    ORDER BY snapshot_at DESC
                    LIMIT 1
                    """
                ),
                {"tenant_id": tenant_id, "resource_id": resource_id},
            ).mappings().first()
        except SQLAlchemyError:
            return (None, None)
        if row is None:
            return (None, None)
        return (_as_decimal_opt(row["current_workload_pct"]), _as_decimal_opt(row["max_workload_pct"]))

    def _persist_employee_profile(self, payload: CreateEmployeeInput, employee_id: UUID) -> None:
        if payload.resource_id is None:
            return
        try:
            with self._session() as session:
                for code in payload.skill_codes:
                    skill_id = uuid4()
                    self._exec(session, 
                        text(
                            """
                            INSERT INTO skills (id, tenant_id, code, name)
                            VALUES (:id, :tenant_id, :code, :name)
                            ON CONFLICT (tenant_id, code) DO NOTHING
                            """
                        ),
                        {
                            "id": skill_id,
                            "tenant_id": payload.tenant_id,
                            "code": code,
                            "name": code,
                        },
                    )
                    skill_row = self._exec(session, 
                        text(
                            """
                            SELECT id FROM skills
                            WHERE tenant_id = :tenant_id AND code = :code
                            """
                        ),
                        {"tenant_id": payload.tenant_id, "code": code},
                    ).first()
                    if skill_row is None:
                        continue
                    self._exec(session, 
                        text(
                            """
                            INSERT INTO resource_skills (tenant_id, resource_id, skill_id, proficiency)
                            VALUES (:tenant_id, :resource_id, :skill_id, 1)
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {
                            "tenant_id": payload.tenant_id,
                            "resource_id": payload.resource_id,
                            "skill_id": skill_row[0],
                        },
                    )
                    self._exec(session, 
                        text(
                            """
                            INSERT INTO workload_snapshots (
                                id, tenant_id, resource_id, snapshot_at, current_workload_pct, max_workload_pct
                            ) VALUES (
                                :id, :tenant_id, :resource_id, CURRENT_TIMESTAMP, :current_workload_pct, :max_workload_pct
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "tenant_id": payload.tenant_id,
                            "resource_id": payload.resource_id,
                            "current_workload_pct": payload.current_workload_pct or Decimal("0"),
                            "max_workload_pct": payload.max_workload_pct or Decimal("100"),
                        },
                    )
                if payload.is_available:
                    self._exec(session, 
                        text(
                            """
                            INSERT INTO resource_availability (
                                id, tenant_id, resource_id, available_from, available_until, reason
                            ) VALUES (
                                :id, :tenant_id, :resource_id, CURRENT_TIMESTAMP, NULL, 'company_directory'
                            )
                            """
                        ),
                        {
                            "id": uuid4(),
                            "tenant_id": payload.tenant_id,
                            "resource_id": payload.resource_id,
                        },
                    )
                session.commit()
        except SQLAlchemyError:
            logger.info(
                "company_directory_profile_optional_tables_skipped",
                extra={"tenant_id": str(payload.tenant_id), "employee_id": str(employee_id)},
            )

    def _employee_from_row(
        self,
        row: Any,
        skills: list[str],
        availability: bool | None,
        workload: tuple[Decimal | None, Decimal | None],
    ) -> EmployeeRecord:
        current, maximum = workload
        is_available = True if availability is None else availability
        email = (row["email"] or "").strip().lower()
        values = dict(
            employee_id=_as_uuid(row["id"]),
            tenant_id=_as_uuid(row["tenant_id"]),
            employee_number=row["employee_number"],
            full_name=row["full_name"],
            email=email or "invalid",
            phone=row.get("phone"),
            department_id=_as_uuid(row["department_id"]),
            role_id=_as_uuid(row["role_id"]),
            manager_employee_id=_as_uuid_opt(row["manager_employee_id"]),
            status=row["status"],
            resource_id=_as_uuid_opt(row["resource_id"]),
            user_id=_as_uuid_opt(row.get("user_id")),
            skill_codes=skills,
            is_available=is_available,
            current_workload_pct=current,
            max_workload_pct=maximum,
        )
        if email and "@" in email:
            return EmployeeRecord(**values)
        values["email"] = email
        return EmployeeRecord.model_construct(**values)


class RestCompanyDirectoryRepository:
    """PostgREST adapter used only when Postgres is in explicit degraded REST mode."""

    def clear(self) -> None:
        return None

    def create_department(self, department: DepartmentRecord) -> DepartmentRecord:
        try:
            rest_insert(
                "departments",
                {
                    "id": str(department.department_id),
                    "tenant_id": str(department.tenant_id),
                    "name": department.name,
                    "code": department.code,
                    "manager_employee_id": None
                    if department.manager_employee_id is None
                    else str(department.manager_employee_id),
                    "status": department.status,
                },
            )
        except Exception as exc:
            raise _unavailable(exc) from exc
        return department

    def create_role(self, role: RoleRecord) -> RoleRecord:
        try:
            rest_insert(
                "roles",
                {
                    "id": str(role.role_id),
                    "tenant_id": str(role.tenant_id),
                    "code": role.code,
                    "name": role.name,
                    "description": role.description,
                    "department_id": None if role.department_id is None else str(role.department_id),
                    "status": role.status,
                },
            )
        except Exception as exc:
            raise _unavailable(exc) from exc
        return role

    def create_employee(self, payload: CreateEmployeeInput) -> EmployeeRecord:
        if self.get_department(tenant_id=payload.tenant_id, department_id=payload.department_id) is None:
            raise InvalidManagerError("department not found in tenant", error_code="DEPARTMENT_NOT_FOUND")
        if self.get_role(tenant_id=payload.tenant_id, role_id=payload.role_id) is None:
            raise InvalidManagerError("role not found in tenant", error_code="ROLE_NOT_FOUND")
        employee_id = payload.employee_id or uuid4()
        try:
            rest_insert(
                "employees",
                {
                    "id": str(employee_id),
                    "tenant_id": str(payload.tenant_id),
                    "employee_number": payload.employee_number,
                    "full_name": payload.full_name,
                    "email": payload.email.strip().lower(),
                    "phone": payload.phone,
                    "department_id": str(payload.department_id),
                    "role_id": str(payload.role_id),
                    "manager_employee_id": None
                    if payload.manager_employee_id is None
                    else str(payload.manager_employee_id),
                    "status": payload.status,
                    "resource_id": None if payload.resource_id is None else str(payload.resource_id),
                },
            )
        except Exception as exc:
            raise _unavailable(exc) from exc
        if payload.user_id is not None:
            self.link_identity(
                IdentityMapping(
                    tenant_id=payload.tenant_id,
                    auth_user_id=payload.user_id,
                    employee_id=employee_id,
                    resource_id=payload.resource_id,
                )
            )
        stored = self.get_employee(tenant_id=payload.tenant_id, employee_id=employee_id)
        if stored is None:
            raise _unavailable(RuntimeError("employee insert did not round-trip"))
        return stored

    def create_authority(self, authority: ApprovalAuthorityRecord) -> ApprovalAuthorityRecord:
        try:
            rest_insert(
                "approval_authorities",
                {
                    "id": str(authority.authority_id),
                    "tenant_id": str(authority.tenant_id),
                    "employee_id": None if authority.employee_id is None else str(authority.employee_id),
                    "role_id": None if authority.role_id is None else str(authority.role_id),
                    "department_id": None if authority.department_id is None else str(authority.department_id),
                    "approval_type": authority.approval_type,
                    "authority_code": authority.authority_code,
                    "max_amount": str(authority.max_amount),
                    "currency": authority.currency,
                    "is_active": authority.is_active,
                },
            )
        except Exception as exc:
            raise _unavailable(exc) from exc
        return authority

    def link_identity(self, mapping: IdentityMapping) -> IdentityMapping:
        try:
            rest_insert(
                "identity_links",
                {
                    "tenant_id": str(mapping.tenant_id),
                    "user_id": str(mapping.auth_user_id),
                    "employee_id": None if mapping.employee_id is None else str(mapping.employee_id),
                    "resource_id": None if mapping.resource_id is None else str(mapping.resource_id),
                    "employee_resource_id": None
                    if mapping.resource_id is None
                    else str(mapping.resource_id),
                },
            )
        except Exception as exc:
            raise _unavailable(exc) from exc
        return mapping

    def link_budget_department(self, link: BudgetDepartmentLink) -> BudgetDepartmentLink:
        if self.get_department(tenant_id=link.tenant_id, department_id=link.department_id) is None:
            raise InvalidManagerError("department not found in tenant", error_code="DEPARTMENT_NOT_FOUND")
        return link

    def get_employee(self, *, tenant_id: UUID, employee_id: UUID) -> EmployeeRecord | None:
        rows = self._select(
            "employees",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "id": f"eq.{employee_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return self._employee_from_rest(rows[0], tenant_id)

    def get_department(self, *, tenant_id: UUID, department_id: UUID) -> DepartmentRecord | None:
        rows = self._select(
            "departments",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "id": f"eq.{department_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        return DepartmentRecord(
            department_id=_as_uuid(row["id"]),
            tenant_id=_as_uuid(row["tenant_id"]),
            name=row["name"],
            code=row["code"],
            manager_employee_id=_as_uuid_opt(row.get("manager_employee_id")),
            status=row.get("status") or "active",
        )

    def get_role(self, *, tenant_id: UUID, role_id: UUID) -> RoleRecord | None:
        rows = self._select(
            "roles",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "id": f"eq.{role_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        return RoleRecord(
            role_id=_as_uuid(row["id"]),
            tenant_id=_as_uuid(row["tenant_id"]),
            name=row["name"],
            code=row["code"],
            description=row.get("description"),
            department_id=_as_uuid_opt(row.get("department_id")),
            status=row.get("status") or "active",
        )

    def list_employees(self, *, tenant_id: UUID) -> list[EmployeeRecord]:
        rows = self._select("employees", {"select": "*", "tenant_id": f"eq.{tenant_id}"})
        return [self._employee_from_rest(row, tenant_id) for row in rows]

    def list_departments(self, *, tenant_id: UUID) -> list[DepartmentRecord]:
        rows = self._select("departments", {"select": "*", "tenant_id": f"eq.{tenant_id}"})
        return [
            DepartmentRecord(
                department_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                name=row["name"],
                code=row["code"],
                manager_employee_id=_as_uuid_opt(row.get("manager_employee_id")),
                status=row.get("status") or "active",
            )
            for row in rows
        ]

    def list_roles(self, *, tenant_id: UUID) -> list[RoleRecord]:
        rows = self._select("roles", {"select": "*", "tenant_id": f"eq.{tenant_id}"})
        return [
            RoleRecord(
                role_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                name=row["name"],
                code=row["code"],
                description=row.get("description"),
                department_id=_as_uuid_opt(row.get("department_id")),
                status=row.get("status") or "active",
            )
            for row in rows
        ]

    def list_authorities(self, *, tenant_id: UUID) -> list[ApprovalAuthorityRecord]:
        rows = self._select(
            "approval_authorities", {"select": "*", "tenant_id": f"eq.{tenant_id}"}
        )
        return [
            ApprovalAuthorityRecord(
                authority_id=_as_uuid(row["id"]),
                tenant_id=_as_uuid(row["tenant_id"]),
                employee_id=_as_uuid_opt(row.get("employee_id")),
                role_id=_as_uuid_opt(row.get("role_id")),
                department_id=_as_uuid_opt(row.get("department_id")),
                approval_type=row["approval_type"],
                authority_code=row.get("authority_code"),
                max_amount=Decimal(str(row["max_amount"])),
                currency=row["currency"],
                is_active=bool(row.get("is_active", True)),
            )
            for row in rows
        ]

    def get_identity_by_user(self, *, tenant_id: UUID, user_id: UUID) -> IdentityMapping | None:
        rows = self._select(
            "identity_links",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "user_id": f"eq.{user_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        return IdentityMapping(
            tenant_id=_as_uuid(row["tenant_id"]),
            auth_user_id=_as_uuid(row["user_id"]),
            employee_id=_as_uuid_opt(row.get("employee_id")),
            resource_id=_as_uuid_opt(row.get("resource_id")),
        )

    def get_identity_by_employee(self, *, tenant_id: UUID, employee_id: UUID) -> IdentityMapping | None:
        rows = self._select(
            "identity_links",
            {
                "select": "*",
                "tenant_id": f"eq.{tenant_id}",
                "employee_id": f"eq.{employee_id}",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        return IdentityMapping(
            tenant_id=_as_uuid(row["tenant_id"]),
            auth_user_id=_as_uuid(row["user_id"]),
            employee_id=_as_uuid_opt(row.get("employee_id")),
            resource_id=_as_uuid_opt(row.get("resource_id")),
        )

    def get_budget_link(self, *, tenant_id: UUID, resource_id: UUID) -> BudgetDepartmentLink | None:
        rows = self._select(
            "budget_resource_profiles",
            {
                "select": "tenant_id,resource_id,department_id",
                "tenant_id": f"eq.{tenant_id}",
                "resource_id": f"eq.{resource_id}",
                "limit": "1",
            },
        )
        if not rows or rows[0].get("department_id") in (None, ""):
            return None
        row = rows[0]
        return BudgetDepartmentLink(
            tenant_id=_as_uuid(row["tenant_id"]),
            resource_id=_as_uuid(row["resource_id"]),
            department_id=_as_uuid(row["department_id"]),
        )

    def _select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        try:
            return rest_select(table, params)
        except Exception as exc:
            raise _unavailable(exc) from exc

    def _employee_from_rest(self, row: dict[str, Any], tenant_id: UUID) -> EmployeeRecord:
        if _as_uuid(row["tenant_id"]) != tenant_id:
            raise CrossTenantDirectoryError("tenant A cannot resolve tenant B directory data")
        identity = None
        if row.get("id"):
            identity = self.get_identity_by_employee(
                tenant_id=tenant_id, employee_id=_as_uuid(row["id"])
            )
        email = (row.get("email") or "").strip().lower()
        values = dict(
            employee_id=_as_uuid(row["id"]),
            tenant_id=_as_uuid(row["tenant_id"]),
            employee_number=row["employee_number"],
            full_name=row["full_name"],
            email=email or "invalid",
            phone=row.get("phone"),
            department_id=_as_uuid(row["department_id"]),
            role_id=_as_uuid(row["role_id"]),
            manager_employee_id=_as_uuid_opt(row.get("manager_employee_id")),
            status=row.get("status") or "active",
            resource_id=_as_uuid_opt(row.get("resource_id")),
            user_id=None if identity is None else identity.auth_user_id,
            skill_codes=[],
            is_available=row.get("status", "active") == "active",
        )
        if email and "@" in email:
            return EmployeeRecord(**values)
        values["email"] = email
        return EmployeeRecord.model_construct(**values)
