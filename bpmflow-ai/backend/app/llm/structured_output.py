"""Parse LLM text into a Pydantic model."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(
    r"^\s*```(?:json|JSON)?\s*\n(?P<body>.*?)\n```\s*$",
    re.DOTALL,
)


class StructuredOutputError(ValueError):
    """Raised when LLM output cannot be parsed or does not match the schema."""


def strip_markdown_fences(text: str) -> str:
    """Remove a wrapping markdown code fence, if present."""
    stripped = (text or "").strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group("body").strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def parse_structured_output(text: str, response_model: type[T]) -> T:
    """Strip fences, load JSON, and validate against `response_model`."""
    cleaned = strip_markdown_fences(text)
    if not cleaned:
        raise StructuredOutputError(
            f"LLM returned empty output; expected JSON for {response_model.__name__}"
        )
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        preview = cleaned[:400].replace("\n", " ")
        raise StructuredOutputError(
            f"LLM output is not valid JSON for {response_model.__name__}: {exc.msg} "
            f"(pos {exc.pos}). Preview: {preview!r}"
        ) from exc

    try:
        return response_model.model_validate(payload)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"LLM JSON did not match {response_model.__name__}: {exc.error_count()} validation "
            f"error(s)\n{exc}"
        ) from exc
