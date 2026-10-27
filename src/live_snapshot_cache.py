"""Inactive prototype: bounded process-shared cache of public JSON feed snapshots.

Not wired into the dashboard/provider. Loaders must enforce their own HTTP
timeouts; this cache does not cancel a loader already running in another thread.
"""

from collections import OrderedDict
from concurrent.futures import Future, TimeoutError
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from threading import RLock
import time


class SnapshotUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotKey:
    provider: str
    game_id: str
    season: str
    season_type: str
    game_date: str
    schema_version: str = "v1"

    def __post_init__(self):
        if not all(isinstance(v, str) and v.strip() for v in vars(self).values()):
            raise ValueError("All public snapshot context fields are required")
        if not self.game_id.isdigit():
            raise ValueError("A canonical numeric game ID is required")
        date.fromisoformat(self.game_date)


@dataclass(frozen=True)
class Snapshot:
    data: dict
    age_seconds: float
    is_stale: bool
    refresh_error_type: str = None
    verified_at: str = None


@dataclass
class _Slot:
    data: dict = None
    fetched: float = 0
    retry_at: float = 0
    error: str = None
    flight: Future = None
    verified_at: str = None


class LiveSnapshotCache:
    def __init__(self, ttl=15, max_age=60, retry_delay=15, max_entries=16,
                 max_payload_bytes=2_000_000, wait_timeout=5, clock=time.monotonic):
        if not 0 < ttl <= max_age or min(retry_delay, wait_timeout) <= 0 or max_entries < 1 or max_payload_bytes < 1:
            raise ValueError("Invalid cache limits")
        self.ttl, self.max_age, self.retry_delay = ttl, max_age, retry_delay
        self.max_entries, self.max_payload_bytes = max_entries, max_payload_bytes
        self.wait_timeout, self.clock = wait_timeout, clock
        self._lock, self._slots = RLock(), OrderedDict()

    def _snapshot(self, slot):
        age = max(0, self.clock() - slot.fetched)
        if slot.data is None or age > self.max_age:
            raise SnapshotUnavailable("No sufficiently recent feed snapshot")
        return Snapshot(deepcopy(slot.data), age, age >= self.ttl, slot.error, slot.verified_at)

    def get(self, key, loader):
        if not isinstance(key, SnapshotKey):
            raise ValueError("Use an explicit SnapshotKey")
        with self._lock:
            if key not in self._slots:
                if len(self._slots) >= self.max_entries:
                    removable = next((k for k, v in self._slots.items() if v.flight is None), None)
                    if removable is None:
                        raise SnapshotUnavailable("Feed refresh capacity reached")
                    del self._slots[removable]
                self._slots[key] = _Slot()
            slot = self._slots[key]
            self._slots.move_to_end(key)
            if slot.data is not None and self.clock() - slot.fetched < self.ttl:
                return self._snapshot(slot)
            if slot.flight is None and self.clock() < slot.retry_at:
                return self._snapshot(slot)
            owner = slot.flight is None
            if owner:
                slot.flight = Future()
            flight = slot.flight
        if not owner:
            try:
                flight.result(timeout=self.wait_timeout)
            except TimeoutError:
                with self._lock:
                    stale = self._snapshot(slot)
                    return Snapshot(stale.data, stale.age_seconds, True, "RefreshInProgress", stale.verified_at)
            with self._lock:
                return self._snapshot(slot)
        try:
            data = loader()
            if not isinstance(data, dict):
                raise ValueError("Expected a public JSON object")
            raw = json.dumps(data, allow_nan=False).encode("utf-8")
            if len(raw) > self.max_payload_bytes:
                raise ValueError("Feed snapshot exceeds size limit")
            data = json.loads(raw)
        except Exception as error:
            with self._lock:
                slot.error = type(error).__name__
                slot.retry_at = self.clock() + self.retry_delay
                slot.flight = None
                flight.set_result(None)  # Waiters inspect the same retained/absent value.
                return self._snapshot(slot)
        except BaseException:
            with self._lock:
                slot.flight = None
                flight.set_result(None)
            raise
        with self._lock:
            slot.data, slot.fetched, slot.error, slot.retry_at = data, self.clock(), None, 0
            slot.verified_at = datetime.now(timezone.utc).isoformat()
            slot.flight = None
            flight.set_result(None)
            return self._snapshot(slot)
