"""Tenant-scoped procurement (Phase 8B). Authoritative vendors, quotations, POs."""

from .exceptions import (
    CrossTenantProcurementError,
    DuplicatePurchaseOrderError,
    InsufficientBudgetError,
    MissingQuotationEvidenceError,
    ProcurementError,
    ProcurementUnavailableError,
    VendorCommunicationUnavailableError,
    VendorNotFoundError,
)
from .repository import InMemoryProcurementRepository
from .schemas import (
    CreatePurchaseOrderInput,
    CreateQuotationInput,
    CreateVendorContactInput,
    CreateVendorInput,
    PurchaseOrderRecord,
    QuotationRecord,
    VendorContactRecord,
    VendorRecord,
)
from .seed import BPMFLOW_DEMO_TENANT_ID, seed_bpmflow_demo_procurement
from .service import (
    ProcurementService,
    configure_procurement,
    get_procurement,
    reset_procurement,
)

__all__ = [
    "BPMFLOW_DEMO_TENANT_ID",
    "CreatePurchaseOrderInput",
    "CreateQuotationInput",
    "CreateVendorContactInput",
    "CreateVendorInput",
    "CrossTenantProcurementError",
    "DuplicatePurchaseOrderError",
    "InMemoryProcurementRepository",
    "InsufficientBudgetError",
    "MissingQuotationEvidenceError",
    "ProcurementError",
    "ProcurementService",
    "ProcurementUnavailableError",
    "PurchaseOrderRecord",
    "QuotationRecord",
    "VendorCommunicationUnavailableError",
    "VendorContactRecord",
    "VendorNotFoundError",
    "VendorRecord",
    "configure_procurement",
    "get_procurement",
    "reset_procurement",
    "seed_bpmflow_demo_procurement",
]
