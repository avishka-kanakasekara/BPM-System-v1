"""Declarative base for BPM ORM models (Agent 3/4).

Kept separate from app.core.database so unit tests can import these models
without creating a database engine.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
