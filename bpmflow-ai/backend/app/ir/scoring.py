"""Shared IR scoring — reuses policy-knowledge BM25 + hash embeddings.

Do not add a second BM25 or embedding implementation.
"""

from app.policy_knowledge.embeddings import cosine_similarity, embed_text
from app.policy_knowledge.retrieval import _bm25_score, _tokenize

tokenize = _tokenize
bm25_score = _bm25_score

__all__ = ["bm25_score", "cosine_similarity", "embed_text", "tokenize"]
