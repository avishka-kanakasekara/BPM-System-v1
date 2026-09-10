"""Unified LLM client — Gemini-first structured output with optional Anthropic fallback.

Agent 1 discovery and any shared `call_llm` callers use this module.
Production must not use MOCK_LLM. Live mode prefers GEMINI_API_KEY.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.structured_output import StructuredOutputError, parse_structured_output

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_llm_responses.json"
_MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_SECONDS = 0.5


def _load_mock_fixtures() -> dict:
    if not _FIXTURE_PATH.is_file():
        raise StructuredOutputError(f"MOCK_LLM is enabled but fixture file is missing: {_FIXTURE_PATH}")
    with _FIXTURE_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _canned_response(response_model: type[T]) -> T:
    fixtures = _load_mock_fixtures()
    payload = fixtures.get(response_model.__name__)
    if payload is None:
        payload = fixtures.get("default")
    if payload is None:
        raise StructuredOutputError(
            f"MOCK_LLM has no canned response for {response_model.__name__}. "
            f"Add a '{response_model.__name__}' entry to {_FIXTURE_PATH.name}."
        )
    return response_model.model_validate(payload)


def _is_transient(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "OverloadedError",
        "ServiceUnavailableError",
    }:
        return True
    status = getattr(exc, "status_code", None)
    if status in {408, 409, 429, 500, 502, 503, 504, 529}:
        return True
    text = str(exc)
    if "RESOURCE_EXHAUSTED" in text or "429" in text:
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def _gemini_configured() -> bool:
    key = (settings.GEMINI_API_KEY or "").strip()
    return bool(key) and not key.startswith("your_")


def _anthropic_configured() -> bool:
    key = (settings.ANTHROPIC_API_KEY or "").strip()
    return bool(key) and not key.startswith("your_")


def _extract_gemini_text(response: object) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    parts: list[str] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(part_text)
    return "\n".join(parts)


def _gemini_text(system_prompt: str, user_content: str) -> str:
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError(
            "The 'google-genai' package is required for Gemini LLM calls. "
            "Install it or configure ANTHROPIC_API_KEY as a fallback."
        ) from exc

    if not _gemini_configured():
        raise RuntimeError("GEMINI_API_KEY is not set.")

    primary = (settings.GEMINI_MODEL_FLASH or "gemini-3.6-flash").strip()
    candidates = []
    for name in (
        primary,
        settings.GEMINI_MODEL_PRO,
        "gemini-3.6-flash",
        "gemini-3-flash-preview",
        "gemini-flash-latest",
    ):
        cleaned = (name or "").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    last_error: BaseException | None = None
    for model in candidates:
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_content,
                config={
                    "system_instruction": system_prompt,
                    "response_mime_type": "application/json",
                },
            )
            raw = _extract_gemini_text(response)
            if raw.strip():
                return raw
            last_error = RuntimeError(f"Gemini model {model} returned empty content")
        except Exception as exc:
            last_error = exc
            err = str(exc)
            # Per-model free-tier quotas: try the next candidate on 429.
            if "404" in err or "NOT_FOUND" in err or "429" in err or "RESOURCE_EXHAUSTED" in err:
                continue
            raise
    if last_error is not None:
        raise RuntimeError(f"Gemini returned no usable content: {last_error}") from last_error
    raise RuntimeError("Gemini returned empty content")


def _anthropic_text(system_prompt: str, user_content: str) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The 'anthropic' package is required when Gemini is unavailable. "
            "Install it or set GEMINI_API_KEY."
        ) from exc

    if not _anthropic_configured():
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    parts = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _provider_text(system_prompt: str, user_content: str) -> tuple[str, str]:
    """Return (raw_text, provider_name). Prefer Gemini when configured."""
    if _gemini_configured():
        return _gemini_text(system_prompt, user_content), "gemini"
    if _anthropic_configured():
        return _anthropic_text(system_prompt, user_content), "anthropic"
    raise RuntimeError(
        "No LLM provider configured. Set GEMINI_API_KEY (preferred) "
        "or ANTHROPIC_API_KEY for process discovery."
    )


def call_llm(system_prompt: str, user_content: str, response_model: type[T]) -> T:
    """Call the LLM and return JSON validated as `response_model`.

    Prefer Gemini when `GEMINI_API_KEY` is set. Anthropic is only used when
    Gemini is not configured. When `MOCK_LLM` is true (development/testing
    only), returns a canned fixture instead of a live API.
    """
    if settings.MOCK_LLM:
        if settings.is_production:
            raise RuntimeError(
                "Process discovery service is unavailable: MOCK_LLM is not allowed in production."
            )
        logger.info(
            "llm_mock",
            extra={"response_model": response_model.__name__},
        )
        return _canned_response(response_model)

    delay = _INITIAL_BACKOFF_SECONDS
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw, provider = _provider_text(system_prompt, user_content)
            logger.info(
                "llm_call",
                extra={
                    "response_model": response_model.__name__,
                    "attempt": attempt,
                    "provider": provider,
                    "model": (
                        settings.GEMINI_MODEL_FLASH
                        if provider == "gemini"
                        else settings.ANTHROPIC_MODEL
                    ),
                },
            )
            return parse_structured_output(raw, response_model)
        except StructuredOutputError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transient(exc):
                logger.warning(
                    "llm_call_failed",
                    extra={
                        "response_model": response_model.__name__,
                        "attempt": attempt,
                        "error": str(exc),
                    },
                )
                raise
            logger.warning(
                "llm_retry",
                extra={
                    "response_model": response_model.__name__,
                    "attempt": attempt,
                    "backoff_seconds": delay,
                    "error": str(exc),
                },
            )
            time.sleep(delay)
            delay *= 2

    raise RuntimeError("LLM call failed") from last_error
