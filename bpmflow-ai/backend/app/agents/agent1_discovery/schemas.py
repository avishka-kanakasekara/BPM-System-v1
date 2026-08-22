"""Pydantic schemas for Agent 1 Process Discovery & Document Intelligence."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadResult(BaseModel):
    file_id: UUID
    status: Literal["accepted", "rejected"]
    rejection_reason: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: int = Field(ge=0)


class PageText(BaseModel):
    page_num: int = Field(ge=1)
    text: str = ""


class ExtractedDocument(BaseModel):
    file_id: UUID
    pages: list[PageText] = Field(default_factory=list)
    extraction_confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: str
    status: Literal["extracted", "failed"] = "extracted"
    failure_reason: Optional[str] = None


DocumentType = Literal[
    "SOP",
    "POLICY",
    "PURCHASE_REQUEST",
    "QUOTATION",
    "INVOICE",
    "EMAIL",
    "OTHER",
]


class DocumentClassification(BaseModel):
    doc_type: DocumentType
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class Entity(BaseModel):
    entity_type: str
    value: str
    source_page: int = Field(ge=1)
    char_span: tuple[int, int]
    confidence: float = Field(ge=0.0, le=1.0)


RelationPredicate = Literal[
    "actor-performs-task",
    "task-precedes-task",
    "rule-controls-task",
]


class Relation(BaseModel):
    subject: str
    predicate: RelationPredicate
    object: str
    source_reference: str
    confidence: float = Field(ge=0.0, le=1.0)


class RelationExtractionResult(BaseModel):
    relations: list[Relation] = Field(default_factory=list)


class FlaggedException(BaseModel):
    case_id: str
    reason: str
    metric: str
    value: float
    threshold: float


class ProcessMiningResult(BaseModel):
    most_frequent_variant: list[str] = Field(default_factory=list)
    avg_waiting_time_per_activity: dict[str, float] = Field(default_factory=dict)
    rework_activities: list[str] = Field(default_factory=list)
    flagged_exceptions: list[FlaggedException] = Field(default_factory=list)


class ProcessActivity(BaseModel):
    name: str
    actor: Optional[str] = None
    system: Optional[str] = None
    avg_duration: Optional[float] = None
    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)


class ProcessRule(BaseModel):
    description: str
    controls_activity: Optional[str] = None
    source_reference: Optional[str] = None


class ProcessDependency(BaseModel):
    predecessor: str
    successor: str
    source_reference: Optional[str] = None


class ProcessException(BaseModel):
    kind: str
    description: str
    case_id: Optional[str] = None


class ProcessJSON(BaseModel):
    process_name: Optional[str] = None
    activities: list[ProcessActivity] = Field(default_factory=list)
    rules: list[ProcessRule] = Field(default_factory=list)
    dependencies: list[ProcessDependency] = Field(default_factory=list)
    exceptions: list[ProcessException] = Field(default_factory=list)
    missing_or_contradictory_fields: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
