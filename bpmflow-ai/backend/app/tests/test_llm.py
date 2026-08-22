"""LLM client helpers and mock mode."""

from app.agents.agent1_discovery.schemas import RelationExtractionResult
from app.llm.client import call_llm
from app.llm.prompts.agent1_relation_extraction import (
    AGENT1_RELATION_EXTRACTION_SYSTEM,
    wrap_evidence,
)
from app.llm.structured_output import StructuredOutputError, parse_structured_output, strip_markdown_fences


def test_strip_markdown_fences_unwraps_json_block():
    raw = '```json\n{"relations": []}\n```'
    assert strip_markdown_fences(raw) == '{"relations": []}'


def test_parse_structured_output_validates_model():
    raw = """
    {"relations": [{"subject": "A", "predicate": "actor-performs-task",
      "object": "B", "source_reference": "page 1", "confidence": 0.9}]}
    """
    result = parse_structured_output(raw, RelationExtractionResult)
    assert result.relations[0].subject == "A"


def test_parse_structured_output_raises_on_invalid_json():
    try:
        parse_structured_output("not-json", RelationExtractionResult)
    except StructuredOutputError as exc:
        assert "not valid JSON" in str(exc)
    else:
        raise AssertionError("expected StructuredOutputError")


def test_call_llm_uses_mock_fixture(monkeypatch):
    from app.core import config
    from app.llm import client as llm_client

    monkeypatch.setattr(config.settings, "MOCK_LLM", True)
    monkeypatch.setattr(llm_client.settings, "MOCK_LLM", True)

    result = call_llm(
        AGENT1_RELATION_EXTRACTION_SYSTEM,
        wrap_evidence("Requester submits a purchase request."),
        RelationExtractionResult,
    )
    assert result.relations
    assert result.relations[0].subject == "Requester"
    assert result.relations[0].predicate == "actor-performs-task"
