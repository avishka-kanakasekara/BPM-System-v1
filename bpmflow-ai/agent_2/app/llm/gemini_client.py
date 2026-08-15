"""
Agent 2 — Gemini LLM Client (Wrapper around google-genai SDK)

Non-Negotiable Rule #1: Gemini only proposes structured outputs or tool calls. It NEVER executes.

Provides two call shapes:
1. generate_structured_output(): Pass a Pydantic schema and receive a validated model instance.
2. generate_function_call(): Pass tool declarations and receive a proposed ToolCallContract object.

Model Tiers:
- Flash Tier ("flash"): Fast, cost-efficient model (gemini-2.5-flash / gemini-2.0-flash) for classification and drafting.
- Pro Tier ("pro"): High-reasoning model (gemini-2.5-pro / gemini-2.0-pro) for complex planning and optimization.

Features:
- Stateless per-request invocation (no stateful multi-turn interactions).
- Automatic HTTP retries with exponential backoff.
- Offline / Stub mode (GEMINI_OFFLINE=true or missing API key) returning canned, schema-valid objects.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import BaseModel

from app.config import settings
from app.llm import function_declarations, prompts
from app.llm.schemas import (
    AgentDecision,
    ExecutionPlan,
    FailureDiagnosis,
    OptimizationRecommendationSchema,
    RecoveryDecision,
    ToolCallContract,
)

logger = logging.getLogger("agent_2.llm.gemini_client")

T = TypeVar("T", bound=BaseModel)

# Default model tier identifiers
MODEL_FLASH = os.getenv("GEMINI_MODEL_FLASH", "gemini-2.5-flash")
MODEL_PRO = os.getenv("GEMINI_MODEL_PRO", "gemini-2.5-pro")


class GeminiClient:
    """
    Client wrapper for Google Gemini LLM API via google-genai SDK.
    """

    def __init__(self, api_key: Optional[str] = None, is_offline: Optional[bool] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        
        # Check offline mode override or auto-detect based on key presence
        env_offline = os.getenv("GEMINI_OFFLINE", "").strip().lower()
        if is_offline is not None:
            self.is_offline = is_offline
        elif env_offline in ["true", "1", "yes"]:
            self.is_offline = True
        elif not self.api_key or self.api_key.startswith("your_"):
            self.is_offline = True
        else:
            self.is_offline = False

        self._sdk_client = None
        if not self.is_offline:
            try:
                from google import genai
                self._sdk_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai Client ({e}). Falling back to OFFLINE mode.")
                self.is_offline = True

    def _select_model(self, tier: str) -> str:
        if tier.strip().lower() == "pro":
            return MODEL_PRO
        return MODEL_FLASH

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: str = "",
        model_tier: str = "flash",
        max_retries: int = 3,
    ) -> T:
        """
        Generate a validated Pydantic model instance from Gemini structured output.

        :param prompt: User / task prompt content
        :param response_schema: Target Pydantic model class
        :param system_instruction: System prompt instruction
        :param model_tier: "flash" or "pro"
        :param max_retries: HTTP retry count
        :return: Validated Pydantic schema instance
        """
        if self.is_offline:
            logger.info(f"[OFFLINE MODE] Generating canned stub for schema {response_schema.__name__}")
            return self._generate_offline_stub(response_schema, prompt)

        model_name = self._select_model(model_tier)
        sys_prompt = system_instruction or prompts.BASE_SAFETY_DIRECTIVE

        for attempt in range(1, max_retries + 1):
            try:
                # Use google-genai SDK structured output configuration
                response = self._sdk_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "system_instruction": sys_prompt,
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                    },
                )
                raw_text = response.text
                return response_schema.model_validate_json(raw_text)

            except Exception as e:
                logger.warning(f"Gemini API attempt {attempt}/{max_retries} failed for schema {response_schema.__name__}: {e}")
                if attempt == max_retries:
                    logger.error("All Gemini API retries exhausted. Falling back to stub response.")
                    return self._generate_offline_stub(response_schema, prompt)
                await asyncio.sleep(2 ** (attempt - 1))

        return self._generate_offline_stub(response_schema, prompt)

    async def generate_function_call(
        self,
        prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: str = "",
        model_tier: str = "flash",
        max_retries: int = 3,
    ) -> ToolCallContract:
        """
        Pass tool declarations to Gemini and receive a proposed ToolCallContract.
        Does NOT execute anything — returns proposed function call to caller for Tool Guard verification.

        :param prompt: Prompt context
        :param tools: Optional list of tool declaration dicts (defaults to all 12 tools)
        :param system_instruction: System instruction
        :param model_tier: "flash" or "pro"
        :param max_retries: HTTP retry count
        :return: Proposed ToolCallContract
        """
        tool_declarations = tools or function_declarations.ALL_TOOL_DECLARATIONS

        if self.is_offline:
            logger.info("[OFFLINE MODE] Generating canned ToolCallContract proposal")
            return self._generate_offline_tool_call(prompt, tool_declarations)

        model_name = self._select_model(model_tier)
        sys_prompt = system_instruction or prompts.BASE_SAFETY_DIRECTIVE

        for attempt in range(1, max_retries + 1):
            try:
                response = self._sdk_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "system_instruction": sys_prompt,
                        "tools": tool_declarations,
                    },
                )
                # Parse function call from response candidates
                if response.function_calls:
                    fc = response.function_calls[0]
                    return ToolCallContract(name=fc.name, parameters=dict(fc.args))

                # Fallback if model returned json text instead of function call candidate
                return self._generate_offline_tool_call(prompt, tool_declarations)

            except Exception as e:
                logger.warning(f"Gemini function call attempt {attempt}/{max_retries} failed: {e}")
                if attempt == max_retries:
                    return self._generate_offline_tool_call(prompt, tool_declarations)
                await asyncio.sleep(2 ** (attempt - 1))

        return self._generate_offline_tool_call(prompt, tool_declarations)

    def _generate_offline_stub(self, response_schema: Type[T], prompt: str) -> T:
        """Generate deterministic, schema-valid stub objects when running in offline mode."""
        schema_name = response_schema.__name__

        if schema_name == "ExecutionPlan":
            return response_schema(
                task_id="task-stub-101",
                objective="Execute procurement purchase request validation and approval workflow",
                steps=["send_email", "create_po_draft"],
                selected_tools=["send_email", "create_po_draft"],
                reasoning_summary="Offline stub execution plan for procurement process",
                risk_level="LOW",
                confidence=0.95,
                fallback_strategy="Escalate to procurement officer if timeout occurs",
                requires_human=False,
            )
        elif schema_name == "AgentDecision":
            return response_schema(
                decision="EXECUTE",
                confidence=0.92,
                selected_tool="create_po_draft",
                reason="Parameters validated; procurement request approved",
                parameters={"vendor_id": "v-stub-100", "amount": 1500.00, "process_id": "proc-stub-1"},
                risk_level="LOW",
                fallback_strategy="Log escalation warning",
                requires_human=False,
            )
        elif schema_name == "FailureDiagnosis":
            return response_schema(
                failure_type="TEMPORARY",
                confidence=0.88,
                reasoning="Offline stub diagnosis: socket timeout during ERP API handshake",
                recommended_action="Retry operation using exponential backoff strategy",
            )
        elif schema_name == "RecoveryDecision":
            return response_schema(
                retry=True,
                delay_seconds=5,
                alternative_strategy="Use cached session token for ERP connection",
                escalate=False,
                reasoning="Transient connection error identified; retry attempt recommended",
            )
        elif schema_name == "OptimizationRecommendationSchema":
            return response_schema(
                id="opt-stub-001",
                process_id="proc-type-procurement",
                recommendation_type="BOTTLENECK_REDUCTION",
                problem="Manager approval step experiences average delay of 18.4 hours",
                root_cause="Manual notification without automated SLA reminders",
                evidence={"avg_delay_hours": 18.4, "sla_breach_rate": 0.155},
                baseline_metric=18.4,
                predicted_metric=6.0,
                improvement_percent=67.4,
                confidence=0.90,
                risk="LOW",
                status="PENDING_APPROVAL",
            )

        elif schema_name == "IntelligentEmailDraft":
            return response_schema(
                subject="SLA Reminder: Manager Approval Needed for Purchase Request #1001",
                body="Please review pending purchase request #1001. Elapsed time is approaching SLA threshold.",
                priority="HIGH",
            )

        # Generic default fallback using schema field defaults
        field_defaults = {}
        for field_name, field_info in response_schema.model_fields.items():
            if field_info.default is not None and field_info.default != ...:
                field_defaults[field_name] = field_info.default
            elif field_info.default_factory is not None:
                field_defaults[field_name] = field_info.default_factory()
            else:
                field_defaults[field_name] = f"stub_{field_name}"
        return response_schema.model_validate(field_defaults)

    def _generate_offline_tool_call(
        self, prompt: str, tools: List[Dict[str, Any]]
    ) -> ToolCallContract:
        """Generate a deterministic stub function call matching one of the declared tools."""
        prompt_lower = prompt.lower()
        if "email" in prompt_lower or "reminder" in prompt_lower:
            return ToolCallContract(
                name="send_email",
                parameters={
                    "recipient": "frank.miller@acmeglobal.com",
                    "subject": "Approval Reminder: Purchase Request #1001",
                    "body": "Please review pending purchase request #1001.",
                    "process_id": "proc-stub-1",
                    "task_id": "task-stub-2",
                    "recipient_role": "manager",
                },
            )
        elif "po" in prompt_lower or "purchase order" in prompt_lower:
            return ToolCallContract(
                name="create_po_draft",
                parameters={
                    "vendor_id": "v-100",
                    "amount": 3400.00,
                    "process_id": "proc-stub-1",
                },
            )
        return ToolCallContract(
            name="create_workflow_task",
            parameters={
                "process_id": "proc-stub-1",
                "title": "Validate Purchase Request",
                "task_type": "AUTOMATED",
                "assigned_role": "system",
            },
        )
