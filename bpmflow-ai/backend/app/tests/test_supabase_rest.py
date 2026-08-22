"""Supabase REST connectivity unit tests (no live network required)."""

from unittest.mock import MagicMock, patch

from app.core import supabase_rest


def test_rest_client_ignores_proxy_env() -> None:
    with patch.object(supabase_rest.settings, "SUPABASE_URL", "https://example.supabase.co"), patch.object(
        supabase_rest.settings, "SUPABASE_SERVICE_ROLE_KEY", "service-role"
    ), patch("app.core.supabase_rest.httpx.Client") as client_cls:
        supabase_rest._client()
        kwargs = client_cls.call_args.kwargs
        assert kwargs.get("trust_env") is False


def test_ping_rest_true_on_success() -> None:
    response = MagicMock()
    response.is_success = True
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = response
    with patch.object(supabase_rest, "supabase_rest_configured", return_value=True), patch.object(
        supabase_rest, "_client", return_value=client
    ):
        assert supabase_rest.ping_rest() is True


def test_ping_rest_false_on_exception() -> None:
    client = MagicMock()
    client.__enter__.side_effect = RuntimeError("network down")
    with patch.object(supabase_rest, "supabase_rest_configured", return_value=True), patch.object(
        supabase_rest, "_client", return_value=client
    ):
        assert supabase_rest.ping_rest() is False
