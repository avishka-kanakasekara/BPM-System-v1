"""Graceful shutdown coordination."""

from __future__ import annotations

import asyncio
import threading

_lock = threading.Lock()
_accepting_requests = True
_in_flight = 0
_drain_event: asyncio.Event | None = None


def accepting_requests() -> bool:
    with _lock:
        return _accepting_requests


def begin_shutdown() -> None:
    global _accepting_requests
    with _lock:
        _accepting_requests = False


def increment_in_flight() -> None:
    with _lock:
        global _in_flight
        _in_flight += 1


def decrement_in_flight() -> None:
    global _in_flight, _drain_event
    with _lock:
        _in_flight = max(0, _in_flight - 1)
        if _in_flight == 0 and _drain_event is not None:
            _drain_event.set()


def in_flight_count() -> int:
    with _lock:
        return _in_flight


async def wait_for_drain(timeout_seconds: float) -> bool:
    """Wait until in-flight requests reach zero or timeout."""
    global _drain_event
    if in_flight_count() == 0:
        return True
    _drain_event = asyncio.Event()
    try:
        await asyncio.wait_for(_drain_event.wait(), timeout=timeout_seconds)
        return True
    except TimeoutError:
        return False
    finally:
        _drain_event = None
