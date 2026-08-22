"""
Agent 2 — Gemini LLM Client (Wrapper around google-genai SDK)

Non-Negotiable Rule #1: Gemini only proposes structured outputs or tool calls. It NEVER executes.

Provides two call shapes:
1. generate_structured_output(): Pass a Pydantic schema and receive a validated model instance.
2. generate_function_call(): Pass tool declarations and receive a proposed ToolCallContract object.

Model Tiers:
- Flash Tier ("flash"): Fast, cost-efficient model (gemini-3.6-flash) for classification and drafting.
- Pro Tier ("pro"): High-reasoning model (gemini-3.6-flash / gemini-3-flash-preview) for complex planning and optimization.

Features:
- Stateless per-request invocation (no stateful multi-turn interactions).
- Automatic HTTP retries with exponential backoff.
- Offline / Stub mode (GEMINI_OFFLINE=true or missing API key) returning canned, schema-valid objects.
"""

import asyncio
import json
import logging
import os
import re
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

QUOTA_MARKERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "quota",
    "rate limit",
    "too many requests",
)

MODEL_FALLBACKS = [
    "gemini-3.6-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-preview",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]


class GeminiClient:
    """
    Client wrapper for Google Gemini LLM API via google-genai SDK.
    """

    def __init__(self, api_key: Optional[str] = None, is_offline: Optional[bool] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        env_offline = os.getenv("GEMINI_OFFLINE", "").strip().lower()
        if is_offline is not None:
            self.is_offline = is_offline
        elif getattr(settings, "GEMINI_OFFLINE", False) or env_offline in ["true", "1", "yes"]:
            self.is_offline = True
        elif not self.api_key or self.api_key.startswith("your_"):
            self.is_offline = True
        else:
            self.is_offline = False

        self._sdk_client = None
        self._working_model = None
        if not self.is_offline:
            try:
                from google import genai
                self._sdk_client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai Client ({e}). Falling back to OFFLINE mode.")
                self.is_offline = True

    def _select_model(self, tier: str) -> str:
        if tier.strip().lower() == "pro":
            return settings.GEMINI_MODEL_PRO or "gemini-3.6-flash"
        return settings.GEMINI_MODEL_FLASH or "gemini-3.6-flash"

    def _model_candidates(self, tier: str) -> List[str]:
        primary = self._select_model(tier)
        ordered = [self._working_model, primary, settings.GEMINI_MODEL_FLASH, settings.GEMINI_MODEL_PRO, *MODEL_FALLBACKS]
        seen = set()
        unique: List[str] = []
        for name in ordered:
            if name and name not in seen:
                unique.append(name)
                seen.add(name)
        return unique

    def _is_quota_error(self, error: Exception) -> bool:
        text = str(error).lower()
        return any(marker.lower() in text for marker in QUOTA_MARKERS)

    def _sanitize_gemini_schema(self, obj: Any) -> Any:
        """Strip JSON Schema fields Gemini Developer API rejects (additionalProperties, etc.)."""
        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for key, value in obj.items():
                if key in {"additionalProperties", "$schema", "title", "default"}:
                    continue
                if key == "type" and isinstance(value, str):
                    out[key] = value.lower()
                else:
                    out[key] = self._sanitize_gemini_schema(value)
            if out.get("type") == "object" and "properties" not in out:
                out["properties"] = {}
            return out
        if isinstance(obj, list):
            return [self._sanitize_gemini_schema(item) for item in obj]
        return obj

    def _pydantic_schema_for_gemini(self, response_schema: Type[BaseModel]) -> Dict[str, Any]:
        return self._sanitize_gemini_schema(response_schema.model_json_schema())

        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for key, value in obj.items():
                if key == "type" and isinstance(value, str):
                    out[key] = value.lower()
                else:
                    out[key] = self._normalize_schema(value)
            return out
        if isinstance(obj, list):
            return [self._normalize_schema(item) for item in obj]
        return obj

    def _sdk_tools(self, declarations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if declarations and isinstance(declarations[0], dict) and "function_declarations" in declarations[0]:
            wrapped = declarations
        else:
            wrapped = [{"function_declarations": declarations}]
        return self._normalize_schema(wrapped)

    def _extract_text(self, response: Any) -> str:
        raw = getattr(response, "text", None)
        if raw:
            return str(raw).strip()
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    return str(text).strip()
        return ""

    def _extract_function_call(self, response: Any) -> Optional[ToolCallContract]:
        calls = getattr(response, "function_calls", None) or []
        if calls:
            fc = calls[0]
            name = getattr(fc, "name", "") or ""
            args = dict(getattr(fc, "args", None) or {})
            if name:
                return ToolCallContract(name=name, parameters=args)
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                fc = getattr(part, "function_call", None)
                if fc:
                    name = getattr(fc, "name", "") or ""
                    args = dict(getattr(fc, "args", None) or {})
                    if name:
                        return ToolCallContract(name=name, parameters=args)
        return None

    def _parse_model_json(self, raw_text: str, response_schema: Type[T]) -> Optional[T]:
        if not raw_text:
            return None
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
        try:
            return response_schema.model_validate_json(cleaned)
        except Exception:
            pass
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return response_schema.model_validate(data)
        except Exception:
            return None
        return None

    def _extract_labeled_value(self, prompt: str, label: str) -> str:
        match = re.search(rf"{re.escape(label)}\s*:\s*([^\n]+)", prompt, flags=re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip().strip("()[],")

    def _infer_tools_from_prompt(self, prompt: str) -> List[str]:
        prompt_lower = prompt.lower()
        if any(k in prompt_lower for k in ("reminder", "email", "notify", "approval pending")):
            return ["send_email"]
        if "quotation" in prompt_lower or "rfq" in prompt_lower:
            return ["request_quotation"]
        if "purchase order" in prompt_lower or "create_po" in prompt_lower or " po " in prompt_lower:
            return ["create_po_draft"]
        if any(k in prompt_lower for k in ("kpi", "bottleneck", "optim")):
            return ["calculate_kpi"]
        if "escalat" in prompt_lower:
            return ["schedule_escalation"]
        return ["send_email"]

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        model_tier: str = "flash",
        max_retries: int = 2,
    ) -> str:
        """
        Generate plain text from Gemini, with automatic fallback to a deterministic
        offline-safe response when the API key is missing, the model is unavailable,
        or the account is rate/quota limited.
        """
        if self.is_offline:
            return self._generate_offline_text(prompt)

        sys_prompt = system_instruction or prompts.BASE_SAFETY_DIRECTIVE
        last_error = None
        for model_name in self._model_candidates(model_tier):
            for attempt in range(1, max_retries + 1):
                try:
                    response = self._sdk_client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={"system_instruction": sys_prompt},
                    )
                    raw_text = self._extract_text(response)
                    if raw_text:
                        self._working_model = model_name
                        return raw_text
                except Exception as e:
                    last_error = e
                    logger.warning(f"Gemini text {model_name} attempt {attempt}/{max_retries} failed: {e}")
                    if self._is_quota_error(e):
                        self.is_offline = True
                        return self._generate_offline_text(prompt)
                    if "404" in str(e) or "NOT_FOUND" in str(e):
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
        logger.error(f"Gemini text generation exhausted models. Last error: {last_error}")
        return self._generate_offline_text(prompt)

    async def generate_structured_output(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: str = "",
        model_tier: str = "flash",
        max_retries: int = 2,
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

        sys_prompt = system_instruction or prompts.BASE_SAFETY_DIRECTIVE
        json_schema = self._pydantic_schema_for_gemini(response_schema)
        last_error = None
        schema_configs = [
            {"response_mime_type": "application/json", "response_json_schema": json_schema},
            {"response_mime_type": "application/json", "response_schema": json_schema},
        ]
        for model_name in self._model_candidates(model_tier):
            for schema_config in schema_configs:
                for attempt in range(1, max_retries + 1):
                    try:
                        response = self._sdk_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config={"system_instruction": sys_prompt, **schema_config},
                        )
                        raw_text = self._extract_text(response)
                        parsed = self._parse_model_json(raw_text, response_schema)
                        if parsed is not None:
                            self._working_model = model_name
                            return parsed
                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"Gemini API {model_name} attempt {attempt}/{max_retries} failed for schema {response_schema.__name__}: {e}"
                        )
                        if self._is_quota_error(e):
                            self.is_offline = True
                            return self._generate_offline_stub(response_schema, prompt)
                        err = str(e)
                        if "404" in err or "NOT_FOUND" in err:
                            break
                        if "additionalProperties" in err:
                            break
                        if attempt < max_retries:
                            await asyncio.sleep(2 ** (attempt - 1))
                else:
                    continue
                if last_error and ("404" in str(last_error) or "NOT_FOUND" in str(last_error)):
                    break
        try:
            json_prompt = (
                prompt
                + "\n\nReturn ONLY valid JSON matching this schema:\n"
                + json.dumps(json_schema)
            )
            raw_text = await self.generate_text(json_prompt, system_instruction=sys_prompt, model_tier=model_tier, max_retries=1)
            parsed = self._parse_model_json(raw_text, response_schema)
            if parsed is not None:
                return parsed
        except Exception as e:
            last_error = e
        logger.error(f"All Gemini structured-output attempts exhausted. Falling back. Last error: {last_error}")
        return self._generate_offline_stub(response_schema, prompt)

    async def generate_function_call(
        self,
        prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_instruction: str = "",
        model_tier: str = "flash",
        max_retries: int = 2,
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

        sys_prompt = system_instruction or prompts.BASE_SAFETY_DIRECTIVE
        last_error = None
        for model_name in self._model_candidates(model_tier):
            for attempt in range(1, max_retries + 1):
                try:
                    response = self._sdk_client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config={
                            "system_instruction": sys_prompt,
                            "tools": self._sdk_tools(tool_declarations),
                        },
                    )
                    if parsed_call:
                        self._working_model = model_name
                        return parsed_call
                    raw_text = self._extract_text(response)
                    parsed = self._parse_tool_call_json(raw_text)
                    if parsed:
                        self._working_model = model_name
                        return parsed
                except Exception as e:
                    last_error = e
                    logger.warning(f"Gemini function call {model_name} attempt {attempt}/{max_retries} failed: {e}")
                    if self._is_quota_error(e):
                        self.is_offline = True
                        return self._generate_offline_tool_call(prompt, tool_declarations)
                    if "404" in str(e) or "NOT_FOUND" in str(e):
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(2 ** (attempt - 1))
        logger.error(f"Gemini function-call attempts exhausted. Falling back. Last error: {last_error}")
        return self._generate_offline_tool_call(prompt, tool_declarations)

    def _parse_tool_call_json(self, raw_text: str) -> Optional[ToolCallContract]:
        if not raw_text:
            return None
        try:
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
            data = json.loads(cleaned)
            if isinstance(data, dict) and "function_call" in data:
                data = data["function_call"]
            name = (data or {}).get("name") or (data or {}).get("tool")
            params = (data or {}).get("parameters") or (data or {}).get("args") or {}
            if name and isinstance(params, dict):
                return ToolCallContract(name=name, parameters=params)
        except Exception:
            return None
        return None

    def _generate_offline_stub(self, response_schema: Type[T], prompt: str) -> T:
        """Generate deterministic, schema-valid stub objects when running in offline mode."""
        schema_name = response_schema.__name__
        process_id = self._extract_labeled_value(prompt, "process_id") or self._extract_labeled_value(prompt, "Process Title")
        task_id = self._extract_labeled_value(prompt, "task_id") or self._extract_labeled_value(prompt, "Task Title")
        if "ID:" in task_id:
            task_id = task_id.split("ID:")[-1].strip(" )")

        if schema_name == "ExecutionPlan":
            tools = self._infer_tools_from_prompt(prompt)
            return response_schema(
                task_id=task_id or "task-offline",
                objective=f"Execute the assigned workflow task using {', '.join(tools)}",
                steps=tools,
                selected_tools=tools,
                reasoning_summary="Offline fallback plan derived from the current task prompt",
                risk_level="LOW",
                confidence=0.8,
                fallback_strategy="Escalate to the assigned manager if the primary tool fails",
                requires_human=False,
            )
        elif schema_name == "AgentDecision":
            tools = self._infer_tools_from_prompt(prompt)
            return response_schema(
                decision="EXECUTE",
                confidence=0.8,
                selected_tool=tools[0],
                reason="Offline fallback selected an allowed tool from the current task context",
                parameters={"process_id": process_id, "task_id": task_id},
                risk_level="LOW",
                fallback_strategy="Log escalation warning",
                requires_human=False,
            )
        elif schema_name == "CycleStepDecision":
            prompt_lower = prompt.lower()
            if "status=success" in prompt_lower and "status=blocked" not in prompt_lower:
                return response_schema(
                    next_action="COMPLETE",
                    selected_tool="",
                    reason="Offline critic: the last successful tool already satisfies the assigned objective",
                    confidence=0.86,
                    parameters={},
                    goal_achieved=True,
                    critic_notes="Objective appears complete; no further allowed tools are required.",
                )
            if "status=blocked" in prompt_lower:
                return response_schema(
                    next_action="ESCALATE",
                    selected_tool="",
                    reason="Offline critic: the action was blocked by policy",
                    confidence=0.95,
                    goal_achieved=False,
                    critic_notes="Do not retry a blocked or forbidden action.",
                )
            tools = self._infer_tools_from_prompt(prompt)
            return response_schema(
                next_action="EXECUTE",
                selected_tool=tools[0],
                reason="Offline critic: the objective is not yet satisfied; propose one more allowed tool",
                confidence=0.72,
                parameters={"process_id": process_id, "task_id": task_id},
                goal_achieved=False,
                critic_notes="Continue with the smallest remaining allowed action.",
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
        process_id = self._extract_labeled_value(prompt, "process_id") or "proc-offline"
        task_id = self._extract_labeled_value(prompt, "task_id") or "task-offline"
        recipient = (
            self._extract_labeled_value(prompt, "assigned_to")
            or self._extract_labeled_value(prompt, "recipient")
            or self._extract_labeled_value(prompt, "requester_email")
        )
        declared_names = [t.get("name", "") for t in tools if isinstance(t, dict)]
        if "email" in prompt_lower or "reminder" in prompt_lower or "send_email" in declared_names[:1]:
            return ToolCallContract(
                name="send_email",
                parameters={
                    "recipient": recipient,
                    "subject": "Action required on assigned workflow task",
                    "body": "Please review the pending task and complete the required action.",
                    "process_id": process_id,
                    "task_id": task_id,
                    "recipient_role": self._extract_labeled_value(prompt, "assigned_role") or "manager",
                },
            )
        if "po" in prompt_lower or "purchase order" in prompt_lower:
            amount_match = re.search(r"amount[^\d]*(\d+(?:\.\d+)?)", prompt_lower)
            return ToolCallContract(
                name="create_po_draft",
                parameters={
                    "vendor_id": self._extract_labeled_value(prompt, "vendor_id") or "vendor-unknown",
                    "amount": float(amount_match.group(1)) if amount_match else 1.0,
                    "process_id": process_id,
                },
            )
        return ToolCallContract(
            name="create_workflow_task",
            parameters={
                "process_id": process_id,
                "title": self._extract_labeled_value(prompt, "task_title") or "Execute assigned task",
                "task_type": "AUTOMATED",
                "assigned_role": self._extract_labeled_value(prompt, "assigned_role") or "system",
            },
        )

    def _generate_offline_text(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if "root cause" in prompt_lower or "bottleneck" in prompt_lower:
            return (
                "The dominant delay is caused by manual approval follow-up and incomplete "
                "request data that forces rework. Adding automated reminders and stronger "
                "input validation should reduce waiting time and repeat handling."
            )
        if "email" in prompt_lower:
            return "Please review the pending task and take the required action within the SLA window."
        return "Fallback offline response generated because Gemini was unavailable."
