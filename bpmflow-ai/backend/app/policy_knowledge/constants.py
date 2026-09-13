"""Company Policy & Knowledge Repository constants."""

from enum import Enum


class PolicyCategory(str, Enum):
    PROCUREMENT = "PROCUREMENT"
    APPROVAL = "APPROVAL"
    BUDGET = "BUDGET"
    AUTHORIZATION = "AUTHORIZATION"
    SLA = "SLA"
    SECURITY = "SECURITY"
    FINANCE = "FINANCE"
    GENERAL = "GENERAL"


class PolicyVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class PolicyRuleType(str, Enum):
    HIGH_VALUE_THRESHOLD = "HIGH_VALUE_THRESHOLD"
    APPROVAL_THRESHOLD = "APPROVAL_THRESHOLD"
    BUDGET_LIMIT = "BUDGET_LIMIT"
    REQUIRED_EVIDENCE = "REQUIRED_EVIDENCE"
    REQUIRED_AUTHORIZATION = "REQUIRED_AUTHORIZATION"
    SEGREGATION_OF_DUTIES = "SEGREGATION_OF_DUTIES"
    SLA = "SLA"


class PolicyRetrievalStatus(str, Enum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICT = "CONFLICT"


class PolicyOperator(str, Enum):
    GT = "GT"
    GTE = "GTE"
    LT = "LT"
    LTE = "LTE"
    EQ = "EQ"
