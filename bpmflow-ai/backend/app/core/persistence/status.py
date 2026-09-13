"""Runtime persistence status — reported, never invisible."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.persistence.policy import PersistenceMode


@dataclass
class PersistenceStatus:
    """Thread-safe snapshot of the active persistence backend."""

    mode: PersistenceMode = PersistenceMode.UNAVAILABLE
    postgres_available: bool = False
    rest_available: bool = False
    last_probe_at: datetime | None = None
    last_error: str | None = None
    degraded: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(
        self,
        *,
        mode: PersistenceMode,
        postgres_available: bool,
        rest_available: bool,
        last_error: str | None = None,
    ) -> None:
        with self._lock:
            self.mode = mode
            self.postgres_available = postgres_available
            self.rest_available = rest_available
            self.last_probe_at = datetime.now(UTC)
            self.last_error = last_error
            self.degraded = mode == PersistenceMode.REST

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode.value,
                "postgres_available": self.postgres_available,
                "rest_available": self.rest_available,
                "degraded": self.degraded,
                "last_probe_at": (
                    self.last_probe_at.isoformat() if self.last_probe_at else None
                ),
                "last_error": self.last_error,
            }


# Process-wide status singleton (updated at startup and by health probes).
persistence_status = PersistenceStatus()
