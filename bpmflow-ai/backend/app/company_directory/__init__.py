"""Tenant-scoped company HR directory (Phase 2)."""

from .exceptions import (
    ApproverNotResolvedError,
    CommunicationRecipientInvalidError,
    CompanyDirectoryUnavailableError,
    CrossTenantDirectoryError,
    DirectoryError,
    EmployeeNotFoundError,
    InvalidManagerError,
    MissingCompanyEmailError,
)
from .repository import InMemoryCompanyDirectoryRepository
from .schemas import (
    ApprovalAuthorityRecord,
    ApproverCandidate,
    CreateEmployeeInput,
    DepartmentRecord,
    EmployeeRecord,
    IdentityMapping,
    RoleRecord,
    SodComparison,
)
from .seed import BPMFLOW_DEMO_TENANT_ID, seed_bpmflow_demo_company
from .service import (
    CompanyDirectoryService,
    configure_company_directory,
    get_company_directory,
    reset_company_directory,
)

__all__ = [
    "ApprovalAuthorityRecord",
    "ApproverCandidate",
    "ApproverNotResolvedError",
    "BPMFLOW_DEMO_TENANT_ID",
    "CompanyDirectoryService",
    "CompanyDirectoryUnavailableError",
    "CommunicationRecipientInvalidError",
    "configure_company_directory",
    "CreateEmployeeInput",
    "CrossTenantDirectoryError",
    "DepartmentRecord",
    "DirectoryError",
    "EmployeeNotFoundError",
    "EmployeeRecord",
    "IdentityMapping",
    "InMemoryCompanyDirectoryRepository",
    "InvalidManagerError",
    "MissingCompanyEmailError",
    "RoleRecord",
    "SodComparison",
    "get_company_directory",
    "reset_company_directory",
    "seed_bpmflow_demo_company",
]
