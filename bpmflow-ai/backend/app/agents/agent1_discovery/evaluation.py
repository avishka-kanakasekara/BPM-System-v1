"""Offline evaluation of Agent 1 extractors against a hand-labelled gold set.

Run from bpmflow-ai/backend:

    python -m app.agents.agent1_discovery.evaluation
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from app.agents.agent1_discovery.extractors import classify_document, extract_entities, extract_relations
from app.agents.agent1_discovery.schemas import ExtractedDocument, PageText, ProcessJSON, ProcessMiningResult
from app.agents.agent1_discovery.service import build_process_json
from app.core.config import settings

_GOLD_PATH = Path(__file__).parent / "fixtures" / "gold.json"


def _norm(value: str) -> str:
    return " ".join((value or "").lower().split())


def _entity_key(item: dict | object) -> tuple[str, str]:
    if isinstance(item, dict):
        return (_norm(item["entity_type"]), _norm(item["value"]))
    return (_norm(item.entity_type), _norm(item.value))


def _relation_key(item: dict | object) -> tuple[str, str, str]:
    if isinstance(item, dict):
        return (_norm(item["subject"]), _norm(item["predicate"]), _norm(item["object"]))
    return (_norm(item.subject), _norm(item.predicate), _norm(item.object))


def _precision_recall(predicted: set, gold: set) -> tuple[float, float]:
    if not predicted and not gold:
        return 1.0, 1.0
    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    return precision, recall


def _doc_from_text(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        file_id=uuid4(),
        pages=[PageText(page_num=1, text=text)],
        extraction_confidence=1.0,
        extraction_method="eval_gold",
        status="extracted",
    )


def _missing_detected(expected: list[str], predicted: list[str]) -> float:
    if not expected:
        return 1.0
    hits = 0
    for label in expected:
        needle = _norm(label)
        if any(needle in _norm(item) for item in predicted):
            hits += 1
    return hits / len(expected)


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def run_eval(gold_path: Path | None = None) -> dict[str, float]:
    """Score extractors against the gold fixture and print a summary table."""
    settings.MOCK_LLM = True
    path = Path(gold_path) if gold_path else _GOLD_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = payload["documents"]

    entity_p, entity_r = [], []
    relation_p, relation_r = [], []
    schema_ok, missing_rates = [], []

    for document in documents:
        extracted = _doc_from_text(document["text"])
        classification = classify_document(extracted)
        entities = extract_entities(extracted, classification.doc_type)
        relations = extract_relations(extracted, entities, classification.doc_type)
        process = build_process_json(entities, relations, ProcessMiningResult())

        try:
            ProcessJSON.model_validate(process.model_dump())
            schema_ok.append(1.0)
        except Exception:
            schema_ok.append(0.0)

        p_ent, r_ent = _precision_recall(
            {_entity_key(item) for item in entities},
            {_entity_key(item) for item in document["entities"]},
        )
        p_rel, r_rel = _precision_recall(
            {_relation_key(item) for item in relations},
            {_relation_key(item) for item in document["relations"]},
        )
        entity_p.append(p_ent)
        entity_r.append(r_ent)
        relation_p.append(p_rel)
        relation_r.append(r_rel)
        missing_rates.append(
            _missing_detected(document.get("expected_missing", []), process.missing_or_contradictory_fields)
        )

    metrics = {
        "entity_precision": _mean(entity_p),
        "entity_recall": _mean(entity_r),
        "relation_precision": _mean(relation_p),
        "relation_recall": _mean(relation_r),
        "processjson_schema_validity": _mean(schema_ok),
        "missing_field_detection_rate": _mean(missing_rates),
        "documents": float(len(documents)),
    }
    _print_table(metrics)
    return metrics


def _print_table(metrics: dict[str, float]) -> None:
    rows = [
        ("documents", f"{int(metrics['documents'])}"),
        ("entity precision", f"{metrics['entity_precision']:.4f}"),
        ("entity recall", f"{metrics['entity_recall']:.4f}"),
        ("relation precision", f"{metrics['relation_precision']:.4f}"),
        ("relation recall", f"{metrics['relation_recall']:.4f}"),
        ("ProcessJSON schema validity", f"{metrics['processjson_schema_validity']:.4f}"),
        ("missing-field detection rate", f"{metrics['missing_field_detection_rate']:.4f}"),
    ]
    width = max(len(name) for name, _ in rows)
    print()
    print("Agent 1 evaluation")
    print("-" * (width + 14))
    for name, value in rows:
        print(f"{name:<{width}}  {value:>10}")
    print()


if __name__ == "__main__":
    run_eval()
