"""Policy retrieval for Agent 4: tenant-scoped BM25-style IR + rule assembly.

Does not decide risk. Returns evidence and structured rules for deterministic
comparison in RiskAnalysisEngine.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from .constants import PolicyCategory, PolicyRetrievalStatus, PolicyRuleType
from .embeddings import cosine_similarity, embed_text
from .repository import PolicyRepository
from .schemas import (
    CompanyPolicyRecord,
    PolicyEvidenceItem,
    PolicyRetrievalResult,
    PolicyRiskSnapshot,
    PolicyRule,
    PolicyVersionRecord,
)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _bm25_score(
    query_tokens: Sequence[str],
    doc_tokens: Sequence[str],
    *,
    avgdl: float,
    df: Counter,
    n_docs: int,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not query_tokens or not doc_tokens or n_docs <= 0:
        return 0.0
    tf = Counter(doc_tokens)
    dl = len(doc_tokens)
    score = 0.0
    for term in query_tokens:
        if term not in tf:
            continue
        n_qi = df.get(term, 0) or 1
        idf = math.log(1 + (n_docs - n_qi + 0.5) / (n_qi + 0.5))
        freq = tf[term]
        denom = freq + k1 * (1 - b + b * dl / max(avgdl, 1.0))
        score += idf * (freq * (k1 + 1)) / denom
    return score


class PolicyRetrievalService:
    """Retrieve active company policy evidence for Agent 4 risk review."""

    def __init__(self, repository: PolicyRepository) -> None:
        self._repository = repository

    async def search(
        self,
        *,
        tenant_id: UUID,
        query: str,
        categories: list[PolicyCategory] | None = None,
        top_k: int = 5,
        as_of: datetime | None = None,
    ) -> PolicyRetrievalResult:
        active = await self._repository.list_active_versions(
            tenant_id, categories=categories, as_of=as_of
        )
        if not active:
            return PolicyRetrievalResult(
                query=query,
                status=PolicyRetrievalStatus.NOT_FOUND,
                message="No active company policies found for tenant/category filters",
                confidence=Decimal("0"),
            )

        query_tokens = _tokenize(query)
        corpus: list[tuple[CompanyPolicyRecord, PolicyVersionRecord, object, list[str]]] = []
        for policy, version in active:
            for chunk in version.chunks:
                tokens = _tokenize(chunk.text_content)
                corpus.append((policy, version, chunk, tokens))

        if not corpus:
            # Active policies exist but have no searchable text — still return rules.
            rules = self._collect_rules(active)
            if not rules:
                return PolicyRetrievalResult(
                    query=query,
                    status=PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE,
                    message="Active policies have no searchable evidence chunks or rules",
                    confidence=Decimal("0"),
                )
            conflict = self._detect_threshold_conflict(rules)
            if conflict:
                return conflict.model_copy(update={"query": query})
            policy, version = active[0]
            return PolicyRetrievalResult(
                query=query,
                status=PolicyRetrievalStatus.FOUND,
                policy_id=policy.id,
                policy_name=policy.name,
                version=version.version_label,
                category=policy.category,
                evidence=[],
                rules=rules,
                confidence=Decimal("0.55"),
                message="Returned structured rules from active policies without text chunks",
            )

        df: Counter = Counter()
        lengths: list[int] = []
        for _, _, _, tokens in corpus:
            lengths.append(len(tokens))
            df.update(set(tokens))
        avgdl = sum(lengths) / max(len(lengths), 1)
        n_docs = len(corpus)

        query_embedding = embed_text(query)
        scored: list[tuple[float, CompanyPolicyRecord, PolicyVersionRecord, object]] = []
        for policy, version, chunk, tokens in corpus:
            vector_score = 0.0
            if chunk.embedding:
                vector_score = max(0.0, cosine_similarity(query_embedding, chunk.embedding))
            bm25 = _bm25_score(query_tokens, tokens, avgdl=avgdl, df=df, n_docs=n_docs)
            # Prefer pgvector-compatible cosine scores when embeddings exist.
            score = vector_score * 2.0 + bm25 if chunk.embedding else bm25
            if policy.category.value.lower() in query.lower():
                score += 0.5
            scored.append((score, policy, version, chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        top = [item for item in scored if item[0] > 0][:top_k]
        if not top:
            top = scored[: min(top_k, len(scored))]

        max_score = max((s for s, *_ in top), default=0.0) or 1.0
        evidence: list[PolicyEvidenceItem] = []
        for score, policy, version, chunk in top:
            evidence.append(
                PolicyEvidenceItem(
                    document_id=version.source_document_id or version.id,
                    policy_id=policy.id,
                    policy_name=policy.name,
                    version=version.version_label,
                    category=policy.category,
                    page=chunk.page_number,
                    section=chunk.section_title,
                    text=chunk.text_content[:1200],
                    relevance_score=round(min(1.0, score / max_score), 4),
                    chunk_id=chunk.id,
                )
            )

        rules = self._collect_rules(active)
        conflict = self._detect_threshold_conflict(rules)
        if conflict:
            return conflict.model_copy(
                update={
                    "query": query,
                    "evidence": evidence,
                }
            )

        # Prefer the highest-scoring policy identity for the primary pointer.
        primary_policy = top[0][1]
        primary_version = top[0][2]
        confidence = Decimal(str(round(min(1.0, 0.45 + (top[0][0] / max(max_score, 1.0)) * 0.55), 4)))

        threshold_rules = [
            r
            for r in rules
            if r.rule_type
            in (PolicyRuleType.HIGH_VALUE_THRESHOLD, PolicyRuleType.APPROVAL_THRESHOLD)
            and r.threshold_value is not None
        ]
        status = (
            PolicyRetrievalStatus.FOUND
            if threshold_rules or evidence
            else PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE
        )
        return PolicyRetrievalResult(
            query=query,
            status=status,
            policy_id=primary_policy.id,
            policy_name=primary_policy.name,
            version=primary_version.version_label,
            category=primary_policy.category,
            evidence=evidence,
            rules=rules,
            confidence=confidence if status is PolicyRetrievalStatus.FOUND else Decimal("0.2"),
            message=None
            if status is PolicyRetrievalStatus.FOUND
            else "Active policies found but no authoritative threshold/evidence rules",
        )

    async def build_risk_snapshot(
        self,
        *,
        tenant_id: UUID,
        purchase_amount: Decimal | None = None,
        available_budget: Decimal | None = None,
        categories: list[PolicyCategory] | None = None,
        as_of: datetime | None = None,
    ) -> PolicyRiskSnapshot:
        query = "procurement approval threshold for purchase amount budget authorization sla evidence"
        if purchase_amount is not None:
            query = f"procurement approval threshold purchase amount {purchase_amount}"
        result = await self.search(
            tenant_id=tenant_id,
            query=query,
            categories=categories
            or [
                PolicyCategory.PROCUREMENT,
                PolicyCategory.APPROVAL,
                PolicyCategory.BUDGET,
                PolicyCategory.AUTHORIZATION,
                PolicyCategory.FINANCE,
                PolicyCategory.SLA,
                PolicyCategory.GENERAL,
            ],
            as_of=as_of,
        )

        high_value = self._first_threshold(
            result.rules, PolicyRuleType.HIGH_VALUE_THRESHOLD
        )
        approval = self._first_threshold(result.rules, PolicyRuleType.APPROVAL_THRESHOLD)
        # If only one threshold style exists, reuse it for both comparisons.
        if high_value is None and approval is not None:
            high_value = approval
        if approval is None and high_value is not None:
            approval = high_value

        required_evidence: list[str] = []
        required_roles: list[str] = []
        sla_hours = None
        enforce_sod = False
        currency = None
        invoice_tolerance = None
        for rule in result.rules:
            if rule.currency and currency is None:
                currency = rule.currency
            if rule.rule_type is PolicyRuleType.REQUIRED_EVIDENCE:
                for item in rule.required_evidence:
                    if item not in required_evidence:
                        required_evidence.append(item)
            if rule.rule_type is PolicyRuleType.REQUIRED_AUTHORIZATION:
                for role in rule.required_roles:
                    if role not in required_roles:
                        required_roles.append(role)
            if rule.rule_type is PolicyRuleType.SLA and rule.sla_hours is not None:
                sla_hours = rule.sla_hours
            if rule.rule_type is PolicyRuleType.SEGREGATION_OF_DUTIES:
                enforce_sod = True
            raw_tol = (rule.metadata_json or {}).get("invoice_amount_tolerance")
            if raw_tol is not None and invoice_tolerance is None:
                invoice_tolerance = Decimal(str(raw_tol))

        status = result.status
        if status is PolicyRetrievalStatus.FOUND and high_value is None and approval is None:
            # Decision-critical purchase without authoritative threshold.
            if purchase_amount is not None:
                status = PolicyRetrievalStatus.INSUFFICIENT_EVIDENCE

        return PolicyRiskSnapshot(
            status=status,
            query=result.query,
            high_value_threshold=high_value,
            approval_threshold=approval,
            currency=currency,
            required_evidence=required_evidence,
            required_roles=required_roles,
            enforce_segregation_of_duties=enforce_sod or True,
            sla_hours=sla_hours,
            available_budget=available_budget,
            evidence=result.evidence,
            rules=result.rules,
            policy_versions=[
                v
                for v in {
                    *(e.version for e in result.evidence),
                    *([result.version] if result.version else []),
                }
                if v
            ],
            confidence=result.confidence,
            message=result.message,
            invoice_amount_tolerance=invoice_tolerance,
        )

    def _collect_rules(
        self, active: Sequence[tuple[CompanyPolicyRecord, PolicyVersionRecord]]
    ) -> list[PolicyRule]:
        rules: list[PolicyRule] = []
        for _, version in active:
            rules.extend(version.rules)
        return rules

    def _first_threshold(
        self, rules: Iterable[PolicyRule], rule_type: PolicyRuleType
    ) -> Decimal | None:
        for rule in rules:
            if rule.rule_type is rule_type and rule.threshold_value is not None:
                return rule.threshold_value
        return None

    def _detect_threshold_conflict(
        self, rules: list[PolicyRule]
    ) -> PolicyRetrievalResult | None:
        thresholds = [
            (r.threshold_value, r.currency, r.required_approval)
            for r in rules
            if r.rule_type
            in (PolicyRuleType.HIGH_VALUE_THRESHOLD, PolicyRuleType.APPROVAL_THRESHOLD)
            and r.threshold_value is not None
        ]
        unique = {(str(t[0]), t[1], t[2]) for t in thresholds}
        if len(unique) <= 1:
            return None
        return PolicyRetrievalResult(
            query="",
            status=PolicyRetrievalStatus.CONFLICT,
            rules=rules,
            confidence=Decimal("0"),
            message=(
                "Multiple active policies define conflicting purchase approval thresholds"
            ),
            conflicting_policy_ids=[],
        )
