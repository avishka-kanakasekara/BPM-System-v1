"""LLM Explanation Enhancement module for Agent 3 with deterministic fallback."""

from dataclasses import dataclass, field
import asyncio
import re
from typing import Any, List, Optional, Protocol
from uuid import UUID

from .explainer_template import ExplanationContext, TemplateExplainer


class LLMExplanationError(Exception):
    """Sanitized exception for LLM explanation generation failures."""
    pass


class ExplanationGenerator(Protocol):
    """Protocol for Agent 3 explanation generators.
    
    All implementations must provide an async generate_explanation method.
    """

    async def generate_explanation(self, context: ExplanationContext) -> str:
        ...


class TemplateExplainerAdapter:
    """Adapter wrapping deterministic TemplateExplainer behind the async ExplanationGenerator protocol.
    
    Retains backward compatibility with the sync TemplateExplainer.
    """

    def __init__(self, template_explainer: Optional[TemplateExplainer] = None):
        self._explainer = template_explainer or TemplateExplainer()

    async def generate_explanation(self, context: ExplanationContext) -> str:
        return self._explainer.generate_explanation(context)


# ============================================================================
# Sanitized Input Data Model & Allowlist Transformer
# ============================================================================

UUID_REGEX = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _sanitize_text(text: str) -> str:
    """Scrub UUIDs and sensitive patterns from raw narrative strings using strict rules."""
    if not text:
        return ""
    scrubbed = UUID_REGEX.sub("[ANONYMIZED_ID]", str(text))
    return scrubbed


@dataclass
class SanitizedCandidateSummary:
    label: str  # Anonymous label e.g. "Candidate 1" (NO candidate names or UUIDs)
    rank: int
    allocation_score_str: str  # Exact Decimal serialized as string
    role_match_str: str
    skill_match_str: str
    availability_score_str: str
    workload_fit_str: str
    authority_match_str: str
    current_workload_pct: str
    projected_workload_pct: str


@dataclass
class SanitizedBudgetSummary:
    sufficient_balance: bool
    cost_centre_match: bool
    currency_match: bool
    validity_period_valid: bool
    within_authorization_limit: bool
    available_balance: str  # Exact Decimal serialized as string e.g. "50000.00"
    required_amount: str    # Exact Decimal serialized as string e.g. "12000.00"
    currency: Optional[str] = None  # Allowlisted ISO currency code (e.g. "USD", "EUR")


@dataclass
class SanitizedExclusionSummary:
    reason_code: str
    description: str


@dataclass
class SanitizedExplanationInput:
    candidates: List[SanitizedCandidateSummary] = field(default_factory=list)
    human_excluded: List[SanitizedExclusionSummary] = field(default_factory=list)
    budget: Optional[SanitizedBudgetSummary] = None
    gaps: List[str] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    limitations: List[str] = field(default_factory=list)
    confidence_str: Optional[str] = None
    requires_human_approval: bool = True


def sanitize_explanation_context(context: ExplanationContext) -> SanitizedExplanationInput:
    """Convert an immutable ExplanationContext into a sanitized, privacy-minimized payload.

    Strict Allowlist Privacy Guarantee:
    - Never includes tenant IDs, requester IDs, candidate names, resource UUIDs,
      correlation IDs, process instance IDs, task IDs, raw evidence dictionaries,
      cost-centre account names, database URLs, or credentials.
    - Exact Decimal numeric values are serialized strictly as strings.
    - Multi-currency preserves ISO currency codes without inventing '$'.
    """
    candidates: List[SanitizedCandidateSummary] = []
    excluded: List[SanitizedExclusionSummary] = []

    if context.human_requirement_result:
        for idx, candidate in enumerate(context.human_requirement_result.eligible_candidates):
            candidates.append(
                SanitizedCandidateSummary(
                    label=f"Candidate {idx + 1}",
                    rank=candidate.rank,
                    allocation_score_str=str(candidate.allocation_score),
                    role_match_str=str(candidate.score_breakdown.role_match),
                    skill_match_str=str(candidate.score_breakdown.skill_match),
                    availability_score_str=str(candidate.score_breakdown.availability_score),
                    workload_fit_str=str(candidate.score_breakdown.workload_fit),
                    authority_match_str=str(candidate.score_breakdown.authority_match),
                    current_workload_pct=str(candidate.current_workload_percentage),
                    projected_workload_pct=str(candidate.projected_workload_percentage),
                )
            )

        for item in context.human_requirement_result.excluded_resources:
            for entry in item.exclusion_reasons:
                reason_code = entry.reason.value if hasattr(entry.reason, "value") else str(entry.reason)
                excluded.append(
                    SanitizedExclusionSummary(
                        reason_code=reason_code,
                        description=_sanitize_text(entry.description),
                    )
                )

    budget_summary: Optional[SanitizedBudgetSummary] = None
    if context.budget_requirement_result and context.budget_requirement_result.budget_validation:
        val = context.budget_requirement_result.budget_validation
        curr = getattr(context, "currency", None)
        budget_summary = SanitizedBudgetSummary(
            sufficient_balance=val.sufficient_balance,
            cost_centre_match=val.cost_centre_match,
            currency_match=val.currency_match,
            validity_period_valid=val.validity_period_valid,
            within_authorization_limit=val.within_authorization_limit,
            available_balance=str(val.available_balance),
            required_amount=str(val.required_amount),
            currency=curr,
        )

    gaps = [
        f"[{gap.gap_type.value if hasattr(gap.gap_type, 'value') else gap.gap_type}] {_sanitize_text(gap.gap_description)}"
        for gap in context.resource_gaps
    ]

    alternatives = [
        f"[{alt.alternative_type.value if hasattr(alt.alternative_type, 'value') else alt.alternative_type}] {_sanitize_text(alt.description)}"
        for alt in context.alternatives
    ]

    limitations = [_sanitize_text(lim) for lim in context.limitations]

    confidence_str = (
        f"{context.confidence * 100:.0f}%" if context.confidence is not None else None
    )

    return SanitizedExplanationInput(
        candidates=candidates,
        human_excluded=excluded,
        budget=budget_summary,
        gaps=gaps,
        alternatives=alternatives,
        limitations=limitations,
        confidence_str=confidence_str,
        requires_human_approval=True,
    )


# ============================================================================
# Prompts Construction
# ============================================================================

SYSTEM_PROMPT = (
    "You are an AI explanation assistant for Agent 3 Resource Allocation System.\n"
    "Your objective is to rephrase pre-computed, deterministic allocation facts into clear narrative prose.\n\n"
    "CRITICAL CONSTRAINTS & RULES:\n"
    "1. Describe only supplied facts.\n"
    "2. Never select or approve a resource.\n"
    "3. Never alter scores, ranks, or recommendation status.\n"
    "4. Never invent evidence or missing data.\n"
    "5. State clearly that human approval is required.\n"
    "6. Return plain text only. Do NOT use markdown formatting, code fences (```), HTML, or JSON.\n"
    "7. Avoid all identifiers and sensitive information (no UUIDs, names, credentials, or URLs).\n"
)


def build_user_prompt(sanitized: SanitizedExplanationInput) -> str:
    """Build deterministic user prompt from sanitized allowlist input data."""
    lines = ["=== ALLOCATION FACT SUMMARY ==="]

    if sanitized.candidates:
        lines.append("\nEligible Candidates:")
        for c in sanitized.candidates:
            lines.append(
                f"- {c.label} (Rank {c.rank}): Total Score {c.allocation_score_str} "
                f"[Role Match: {c.role_match_str}, Skill Match: {c.skill_match_str}, "
                f"Availability: {c.availability_score_str}, Workload Fit: {c.workload_fit_str}, "
                f"Authority Match: {c.authority_match_str}]. "
                f"Workload: {c.current_workload_pct}% current, {c.projected_workload_pct}% projected."
            )
    else:
        lines.append("\nEligible Candidates: None found.")

    if sanitized.human_excluded:
        lines.append("\nExcluded Candidates Summary:")
        for ex in sanitized.human_excluded:
            lines.append(f"- Reason: {ex.reason_code} ({ex.description})")

    if sanitized.budget:
        b = sanitized.budget
        curr_str = f" {b.currency}" if b.currency else ""
        lines.append("\nBudget Validation Summary:")
        lines.append(
            f"- Available Balance: {b.available_balance}{curr_str}, Required Amount: {b.required_amount}{curr_str}. "
            f"Checks: Sufficient Balance={b.sufficient_balance}, Cost Centre Match={b.cost_centre_match}, "
            f"Currency Match={b.currency_match}, Validity Period={b.validity_period_valid}, "
            f"Authorization Limit={b.within_authorization_limit}."
        )

    if sanitized.gaps:
        lines.append("\nResource Gaps Detected:")
        for gap in sanitized.gaps:
            lines.append(f"- {gap}")

    if sanitized.alternatives:
        lines.append("\nSuggested Alternatives:")
        for alt in sanitized.alternatives:
            lines.append(f"- {alt}")

    if sanitized.limitations:
        lines.append("\nSystem Limitations:")
        for lim in sanitized.limitations:
            lines.append(f"- {lim}")

    if sanitized.confidence_str:
        lines.append(f"\nCalculated Confidence: {sanitized.confidence_str}")

    lines.append("\nDecision Requirement: Human approval is required before execution.")
    return "\n".join(lines)


# ============================================================================
# Output Pattern Validator
# ============================================================================

class LLMOutputValidator:
    """Validates LLM output against structural rules, character bounds, and forbidden patterns.

    Safety Guarantee:
    - Enforces text format constraints, maximum character bounds, forbidden pattern filters (UUIDs, URLs, credentials),
      and mandatory human-approval wording.
    - Does NOT claim semantic fact verification of arbitrary natural language prose.
    - Deterministic pipeline fields (candidate ordering, scores, statuses, approval requirements) remain authoritative.
    """

    CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    CODE_FENCE_REGEX = re.compile(r"```")
    URL_REGEX = re.compile(r"https?://|ftp://", re.IGNORECASE)
    SECRET_REGEX = re.compile(
        r"sk-[a-zA-Z0-9_\-]{15,}|bearer\s+[a-zA-Z0-9\._\-]+|postgres://|DATABASE_URL",
        re.IGNORECASE,
    )

    def validate(self, output: Any, context: ExplanationContext) -> bool:
        """Validate LLM output text. Returns True if accepted, False otherwise."""
        if not isinstance(output, str):
            return False

        stripped = output.strip()
        if not stripped:
            return False

        if len(output) > 4000:
            return False

        if self.CONTROL_CHAR_REGEX.search(output):
            return False

        if self.CODE_FENCE_REGEX.search(output):
            return False

        if UUID_REGEX.search(output):
            return False

        if self.URL_REGEX.search(output):
            return False

        if self.SECRET_REGEX.search(output):
            return False

        # Must explicitly acknowledge human approval requirement
        lower_out = output.lower()
        if "human approval" not in lower_out and "approval required" not in lower_out:
            return False

        return True


# ============================================================================
# OpenAI Explanation Generator (Responses API)
# ============================================================================

class OpenAIExplanationGenerator:
    """Optional OpenAI LLM explanation generator using the official Responses API.

    Notes:
    - Model parameter is configurable via dependency injection (default: "gpt-4o-mini").
    - Production deployments may inject a pinned snapshot (e.g., "gpt-4o-mini-2024-07-18") for reproducibility.
    - Temperature parameter is optional (default: None). Included only when caller explicitly configures it.
    - Uses client.responses.create(...) with instructions=, input=, max_output_tokens=, store=False.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        model: str = "gpt-4o-mini",
        timeout: float = 5.0,
        max_output_tokens: int = 500,
        temperature: Optional[float] = None,
    ):
        self.client = client
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.temperature = temperature

    async def generate_explanation(self, context: ExplanationContext) -> str:
        """Generate enhanced explanation via OpenAI client using Responses API."""
        if self.client is None:
            raise LLMExplanationError("OpenAI client not configured")

        sanitized_input = sanitize_explanation_context(context)
        user_prompt = build_user_prompt(sanitized_input)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "instructions": SYSTEM_PROMPT,
            "input": user_prompt,
            "max_output_tokens": self.max_output_tokens,
            "store": False,
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        try:
            # Execute client.responses.create bounded by explicit timeout
            response = await asyncio.wait_for(
                self.client.responses.create(**kwargs),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            raise LLMExplanationError("LLM request timed out") from None
        except Exception:
            # Sanitize exception: never expose API keys, prompt payloads, or internal traces
            raise LLMExplanationError("LLM generation request failed") from None

        try:
            if not response:
                raise LLMExplanationError("Empty response object")

            # Extract output_text safely without assuming specific indexing
            output_text = getattr(response, "output_text", None)
            if output_text is None and hasattr(response, "output"):
                output_list = getattr(response, "output", None)
                if isinstance(output_list, list) and output_list:
                    first = output_list[0]
                    output_text = getattr(first, "text", None) or getattr(first, "content", None)

            if output_text is None or not isinstance(output_text, str):
                raise LLMExplanationError("Invalid or missing output_text in response")

            return output_text
        except (AttributeError, IndexError, TypeError):
            raise LLMExplanationError("Invalid response structure") from None


# ============================================================================
# Resilient Fallback Wrapper
# ============================================================================

class ResilientFallbackExplainer:
    """Resilient fallback wrapper around optional LLM explanation generator.

    Guarantees:
    - Never throws an exception to caller.
    - Performs zero internal retries.
    - Never changes recommendation status, candidates, scores, or approval flags.
    - Always falls back to deterministic TemplateExplainerAdapter on any error/validation failure.
    """

    def __init__(
        self,
        enabled: bool = False,
        llm_generator: Optional[ExplanationGenerator] = None,
        template_explainer: Optional[ExplanationGenerator] = None,
        validator: Optional[LLMOutputValidator] = None,
    ):
        self.enabled = enabled
        self.llm_generator = llm_generator
        self.template_explainer = template_explainer or TemplateExplainerAdapter()
        self.validator = validator or LLMOutputValidator()

    async def generate_explanation(self, context: ExplanationContext) -> str:
        """Generate explanation using LLM if enabled/valid, otherwise fallback to template."""
        if not self.enabled or self.llm_generator is None:
            return await self.template_explainer.generate_explanation(context)

        try:
            # Call LLM generator exactly once (no retries)
            llm_output = await self.llm_generator.generate_explanation(context)
            if self.validator.validate(llm_output, context):
                return llm_output.strip()
        except Exception:
            # Catch all LLM/network/timeout/sdk failures silently
            pass

        # Fallback to deterministic template explanation
        return await self.template_explainer.generate_explanation(context)
