"""Thin Anthropic wrapper with structured output and optional mock mode."""

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
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def _anthropic_text(system_prompt: str, user_content: str) -> str:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError(
            "The 'anthropic' package is required when MOCK_LLM is false. "
            "Install it or set MOCK_LLM=true."
        ) from exc

    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to .env or enable MOCK_LLM.")

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


def call_llm(system_prompt: str, user_content: str, response_model: type[T]) -> T:
    """Call the LLM and return JSON validated as `response_model`.

    When `settings.MOCK_LLM` is true, returns a canned fixture instead of the API.
    """
    if settings.MOCK_LLM:
        logger.info(
            "llm_mock",
            extra={"response_model": response_model.__name__},
        )
        return _canned_response(response_model)

    delay = _INITIAL_BACKOFF_SECONDS
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            logger.info(
                "llm_call",
                extra={
                    "response_model": response_model.__name__,
                    "attempt": attempt,
                    "model": settings.ANTHROPIC_MODEL,
                },
            )
            raw = _anthropic_text(system_prompt, user_content)
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
