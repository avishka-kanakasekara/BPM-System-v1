"""Information retrieval helpers.

Policy retrieval reuses BM25-style scoring in
``app.policy_knowledge.retrieval`` rather than inventing a second IR stack.
Agent 2 process memory remains available for execution evidence.
"""

from app.policy_knowledge.retrieval import PolicyRetrievalService

__all__ = ["PolicyRetrievalService"]
