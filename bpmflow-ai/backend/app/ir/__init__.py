"""Information retrieval helpers.

Policy retrieval and Agent 1 document search share BM25 + hash-vector scoring
from ``app.policy_knowledge`` rather than inventing a second IR stack.
Agent 2 process memory remains available for execution evidence.
"""

from app.ir.corpus import DocumentCorpus, get_document_corpus, reset_document_corpus
from app.ir.hybrid import hybrid_search
from app.policy_knowledge.retrieval import PolicyRetrievalService

__all__ = [
    "DocumentCorpus",
    "PolicyRetrievalService",
    "get_document_corpus",
    "hybrid_search",
    "reset_document_corpus",
]
