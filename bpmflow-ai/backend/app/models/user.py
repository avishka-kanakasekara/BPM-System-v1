"""SQLAlchemy model for public.users (linked to Supabase auth.users)."""

from sqlalchemy import Column, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class User(Base):
    """Application user profile. id matches auth.users.id / JWT sub."""

    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id = Column(UUID(as_uuid=True), primary_key=True)
    email = Column(Text, nullable=False, unique=True)
    full_name = Column(Text)
    role = Column(Text, nullable=False, default="requester")
    department = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
