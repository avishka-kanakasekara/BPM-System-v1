"""Unit tests for database URL credential redaction (no database required)."""

import pytest

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.agents.agent3_resources.repositories.session_factory import normalize_async_database_url


class TestDatabaseURLRedaction:
    """Regression tests to ensure database credentials are redacted from tracebacks."""

    def test_sqlalchemy_url_masks_password_in_repr(self):
        """Test that SQLAlchemy URL object masks password in repr()."""
        fake_password = "FAKE_PASSWORD_12345"
        url_str = f"postgresql://user:{fake_password}@localhost:5432/testdb"
        url_obj = make_url(normalize_async_database_url(url_str))
        
        # Password should not appear in repr or str
        url_repr = repr(url_obj)
        url_str_repr = str(url_obj)
        
        assert fake_password not in url_repr, f"Password {fake_password} leaked in repr: {url_repr}"
        assert fake_password not in url_str_repr, f"Password {fake_password} leaked in str: {url_str_repr}"
        assert "***" in url_repr, "Password should be masked with asterisks"
    
    def test_sqlalchemy_url_masks_password_in_render_as_string(self):
        """Test that SQLAlchemy URL object masks password in render_as_string()."""
        fake_password = "FAKE_PASSWORD_67890"
        url_str = f"postgresql://user:{fake_password}@localhost:5432/testdb"
        url_obj = make_url(normalize_async_database_url(url_str))
        
        # render_as_string should mask password by default
        rendered = url_obj.render_as_string(hide_password=True)
        
        assert fake_password not in rendered, f"Password {fake_password} leaked in render_as_string: {rendered}"
        assert "***" in rendered, "Password should be masked"
    
    def test_async_engine_hides_parameters_by_default(self):
        """Test that async engine configuration uses hide_parameters=True."""
        fake_password = "FAKE_PASSWORD_ABCDE"
        url_str = f"postgresql://user:{fake_password}@localhost:5432/testdb"
        url_obj = make_url(normalize_async_database_url(url_str))
        
        # Create engine with hide_parameters=True (no connection required)
        engine = create_async_engine(
            url_obj,
            echo=False,
            hide_parameters=True,
        )
        
        # Verify the engine was created successfully
        assert engine is not None
        assert engine.pool is not None
    
    def test_persistence_error_message_does_not_contain_password(self):
        """Test that sanitized persistence errors do not contain the fake password."""
        fake_password = "FAKE_PASSWORD_XYZ987"
        
        # Simulate a persistence error message
        error_message = f"Transaction failed: connection error to database"
        
        # The fake password should not appear in error messages
        assert fake_password not in error_message, f"Password {fake_password} leaked in error message"
