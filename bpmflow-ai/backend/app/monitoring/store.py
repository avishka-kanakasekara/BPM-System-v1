"""In-memory tenant-scoped monitoring corpus for tests and same-process APIs."""

from __future__ import annotations

from threading import Lock
from uuid import UUID

from app.monitoring.records import MonitoringProcess
from app.monitoring.schemas import TobeRecommendationRecord


class MonitoringStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._processes: dict[tuple[UUID, UUID], MonitoringProcess] = {}
        self._recommendations: dict[tuple[UUID, UUID], TobeRecommendationRecord] = {}
        self._fingerprints: dict[tuple[UUID, str], UUID] = {}

    def reset(self) -> None:
        with self._lock:
            self._processes.clear()
            self._recommendations.clear()
            self._fingerprints.clear()

    def upsert_process(self, record: MonitoringProcess) -> MonitoringProcess:
        with self._lock:
            self._processes[(record.tenant_id, record.process_id)] = record
            return record

    def get_process(self, tenant_id: UUID, process_id: UUID) -> MonitoringProcess | None:
        with self._lock:
            return self._processes.get((tenant_id, process_id))

    def list_processes(self, tenant_id: UUID) -> list[MonitoringProcess]:
        with self._lock:
            return [item for (tid, _), item in self._processes.items() if tid == tenant_id]

    def upsert_recommendation(self, record: TobeRecommendationRecord) -> TobeRecommendationRecord:
        with self._lock:
            existing_id = self._fingerprints.get((record.tenant_id, record.fingerprint))
            if existing_id is not None:
                existing = self._recommendations.get((record.tenant_id, existing_id))
                if existing is not None:
                    return existing
            self._recommendations[(record.tenant_id, record.id)] = record
            self._fingerprints[(record.tenant_id, record.fingerprint)] = record.id
            return record

    def replace_recommendation(self, record: TobeRecommendationRecord) -> TobeRecommendationRecord:
        with self._lock:
            self._recommendations[(record.tenant_id, record.id)] = record
            return record

    def get_recommendation(self, tenant_id: UUID, recommendation_id: UUID) -> TobeRecommendationRecord | None:
        with self._lock:
            return self._recommendations.get((tenant_id, recommendation_id))

    def list_recommendations(
        self, tenant_id: UUID, *, process_id: UUID | None = None
    ) -> list[TobeRecommendationRecord]:
        with self._lock:
            items = [item for (tid, _), item in self._recommendations.items() if tid == tenant_id]
        if process_id is not None:
            items = [item for item in items if item.process_id == process_id]
        return items


_STORE = MonitoringStore()


def get_monitoring_store() -> MonitoringStore:
    return _STORE


def reset_monitoring_store() -> None:
    _STORE.reset()
