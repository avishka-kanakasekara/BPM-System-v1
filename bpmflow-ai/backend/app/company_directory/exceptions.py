"""Company directory errors. Missing facts stay explicit — never invented."""

from __future__ import annotations


class DirectoryError(ValueError):
    error_code = "DIRECTORY_ERROR"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        self.error_code = error_code or self.error_code
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {"error_code": self.error_code, "message": str(self)}


class CrossTenantDirectoryError(DirectoryError):
    error_code = "CROSS_TENANT_DENIED"


class InvalidManagerError(DirectoryError):
    error_code = "INVALID_MANAGER"


class ApproverNotResolvedError(DirectoryError):
    error_code = "APPROVER_NOT_RESOLVED"


class EmployeeNotFoundError(DirectoryError):
    error_code = "EMPLOYEE_NOT_FOUND"


class ResourceNotFoundError(DirectoryError):
    error_code = "RESOURCE_NOT_FOUND"


class MissingCompanyEmailError(DirectoryError):
    error_code = "MISSING_COMPANY_EMAIL"


class IdentityNotResolvedError(DirectoryError):
    error_code = "IDENTITY_NOT_RESOLVED"


class CompanyDirectoryUnavailableError(DirectoryError):
    error_code = "COMPANY_DIRECTORY_UNAVAILABLE"


class CommunicationRecipientInvalidError(DirectoryError):
    error_code = "COMMUNICATION_RECIPIENT_INVALID"


class EmailProviderNotConfiguredError(DirectoryError):
    error_code = "EMAIL_PROVIDER_NOT_CONFIGURED"
