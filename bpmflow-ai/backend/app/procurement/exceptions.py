"""Procurement persistence errors. Missing facts stay explicit."""

from __future__ import annotations


class ProcurementError(ValueError):
    error_code = "PROCUREMENT_ERROR"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        self.error_code = error_code or self.error_code
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {"error_code": self.error_code, "message": str(self)}


class VendorNotFoundError(ProcurementError):
    error_code = "VENDOR_NOT_FOUND"


class QuotationNotFoundError(ProcurementError):
    error_code = "QUOTATION_NOT_FOUND"


class PurchaseOrderNotFoundError(ProcurementError):
    error_code = "PURCHASE_ORDER_NOT_FOUND"


class CrossTenantProcurementError(ProcurementError):
    error_code = "CROSS_TENANT_DENIED"


class InsufficientBudgetError(ProcurementError):
    error_code = "INSUFFICIENT_BUDGET"


class MissingQuotationEvidenceError(ProcurementError):
    error_code = "MISSING_QUOTATION_EVIDENCE"


class DuplicatePurchaseOrderError(ProcurementError):
    error_code = "DUPLICATE_PURCHASE_ORDER"


class ProcurementUnavailableError(ProcurementError):
    error_code = "PROCUREMENT_UNAVAILABLE"


class VendorCommunicationUnavailableError(ProcurementError):
    error_code = "VENDOR_COMMUNICATION_NOT_AVAILABLE"


class InvoiceNotFoundError(ProcurementError):
    error_code = "MISSING_INVOICE"


class InvoiceTotalInvalidError(ProcurementError):
    error_code = "INVOICE_TOTAL_INVALID"


class InvoiceMatchError(ProcurementError):
    error_code = "INVOICE_MISMATCH"
