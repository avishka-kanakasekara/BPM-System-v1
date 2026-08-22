"""Declarative base for SQLAlchemy ORM models.

Kept separate from app.core.database engine creation so unit tests can import
models without requiring DATABASE_URL.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
