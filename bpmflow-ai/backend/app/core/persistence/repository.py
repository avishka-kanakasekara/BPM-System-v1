"""Central persistence routing — Postgres primary, REST fallback."""

from __future__ import annotations

from typing import Literal

from app.core.config import settings
from app.core.logging import get_logger
from app.core.persistence.policy import OperationKind, PersistenceMode, may_use_rest_fallback
from app.core.persistence.status import persistence_status

logger = get_logger(__name__)

Backend = Literal["postgres", "rest"]


class PersistenceError(RuntimeError):
    """Raised when a required backend is unavailable."""

    def __init__(self, message: str, *, mode: PersistenceMode | None = None) -> None:
        super().__init__(message)
        self.mode = mode or persistence_status.mode


def _configured_rest() -> bool:
    from app.core.supabase_rest import supabase_rest_configured

    return supabase_rest_configured()


def _postgres_reachable() -> bool:
    from app.core.database import probe_postgres_sync

    return probe_postgres_sync(timeout_seconds=settings.HEALTH_PROBE_TIMEOUT_SECONDS)


def _rest_reachable() -> bool:
    from app.core.supabase_rest import ping_rest

    if not _configured_rest():
        return False
    return ping_rest(timeout_seconds=settings.HEALTH_PROBE_TIMEOUT_SECONDS)


def probe_and_update_status() -> PersistenceMode:
    """Probe backends and update the global ``persistence_status``."""
    mode_setting = settings.PERSISTENCE_MODE.lower()
    pg_ok = _postgres_reachable()
    rest_ok = _rest_reachable()
    last_error: str | None = None

    if mode_setting == "postgres":
        if pg_ok:
            mode = PersistenceMode.POSTGRES
        else:
            mode = PersistenceMode.UNAVAILABLE
            last_error = "Postgres required but unreachable"
    elif mode_setting == "rest":
        if rest_ok:
            mode = PersistenceMode.REST
        else:
            mode = PersistenceMode.UNAVAILABLE
            last_error = "REST required but unreachable"
    else:
        # auto — prefer Postgres, fall back to REST (degraded).
        if pg_ok:
            mode = PersistenceMode.POSTGRES
        elif rest_ok:
            mode = PersistenceMode.REST
            logger.warning("persistence_degraded_using_rest")
        else:
            mode = PersistenceMode.UNAVAILABLE
            last_error = "Neither Postgres nor Supabase REST is reachable"

    persistence_status.update(
        mode=mode,
        postgres_available=pg_ok,
        rest_available=rest_ok,
        last_error=last_error,
    )
    return mode


def get_effective_mode() -> PersistenceMode:
    if persistence_status.last_probe_at is None:
        return probe_and_update_status()
    return persistence_status.mode


def resolve_backend(kind: OperationKind) -> Backend:
    """Return the backend to use for *kind*, or raise ``PersistenceError``."""
    mode = get_effective_mode()

    if requires_postgres(kind):
        assert_postgres_available()
        return "postgres"

    if mode == PersistenceMode.POSTGRES:
        return "postgres"

    if mode == PersistenceMode.REST and may_use_rest_fallback(kind):
        return "rest"

    raise PersistenceError(
        f"Persistence unavailable for {kind.value} (mode={mode.value})",
        mode=mode,
    )


def requires_postgres(kind: OperationKind) -> bool:
    from app.core.persistence.policy import requires_postgres as _requires

    return _requires(kind)


def assert_postgres_available() -> None:
    mode = get_effective_mode()
    if mode != PersistenceMode.POSTGRES:
        raise PersistenceError(
            "Postgres is required for this operation but is unavailable",
            mode=mode,
        )
