"""Pydantic schemas for Agent 1 Process Discovery & Document Intelligence."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UploadResult(BaseModel):
    file_id: UUID
    status: Literal["accepted", "rejected"]
    rejection_reason: str | None = None
    mime_type: str | None = None
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
    failure_reason: str | None = None


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


class DiscoveredStep(BaseModel):
    """One intelligently selected process step from document analysis."""

    name: str = Field(min_length=1)
    order: int = Field(ge=1)
    required: bool = True
    actor_hint: str | None = None
    rationale: str = ""
    source_reference: str = ""
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class RejectedStepCandidate(BaseModel):
    name: str = Field(min_length=1)
    reason: str = ""


class StepSelectionResult(BaseModel):
    """LLM/heuristic result: required steps for this process only."""

    process_name: str | None = None
    steps: list[DiscoveredStep] = Field(default_factory=list)
    rejected_candidates: list[RejectedStepCandidate] = Field(default_factory=list)
    selection_summary: str = ""


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
    # Fallback analytics when timing is weak or missing.
    activity_event_counts: dict[str, int] = Field(default_factory=dict)
    activity_case_counts: dict[str, int] = Field(default_factory=dict)
    total_cases: int = 0
    total_events: int = 0
    timing_available: bool = False


class ProcessActivity(BaseModel):
    name: str
    actor: str | None = None
    system: str | None = None
    avg_duration: float | None = None
    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)
    # Duration provenance + non-time analytics for UI fallbacks.
    duration_source: str | None = None  # measured | estimated_text | unavailable
    duration_note: str | None = None
    occurrence_count: int | None = None
    case_count: int | None = None
    case_coverage: float | None = None  # 0..1
    on_main_path: bool = False
    is_rework: bool = False


class ProcessRule(BaseModel):
    description: str
    controls_activity: str | None = None
    source_reference: str | None = None


class ProcessDependency(BaseModel):
    predecessor: str
    successor: str
    source_reference: str | None = None


class ProcessException(BaseModel):
    kind: str
    description: str
    case_id: str | None = None


class StageExecutionMeta(BaseModel):
    """Per-stage execution metadata for degraded/offline discovery paths."""

    degraded: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    method: str = ""


class ProcessJSON(BaseModel):
    process_name: str | None = None
    activities: list[ProcessActivity] = Field(default_factory=list)
    rules: list[ProcessRule] = Field(default_factory=list)
    dependencies: list[ProcessDependency] = Field(default_factory=list)
    exceptions: list[ProcessException] = Field(default_factory=list)
    missing_or_contradictory_fields: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    analytics: dict[str, Any] = Field(default_factory=dict)
