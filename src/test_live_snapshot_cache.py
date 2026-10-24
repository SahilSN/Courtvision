from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
import unittest
from unittest.mock import Mock

from live_snapshot_cache import LiveSnapshotCache, SnapshotKey, SnapshotUnavailable


KEY = SnapshotKey("espn", "0022600001", "2026-27", "Regular Season", "2026-10-23")


class LiveSnapshotCacheTest(unittest.TestCase):
    def test_concurrent_viewers_share_one_refresh_and_copies(self):
        entered, release = Event(), Event()
        def load():
            entered.set()
            self.assertTrue(release.wait(3))
            return {"scores": [1, 2]}
        loader = Mock(side_effect=load)
        cache = LiveSnapshotCache()
        with ThreadPoolExecutor(max_workers=12) as pool:
            owner = pool.submit(cache.get, KEY, loader)
            self.assertTrue(entered.wait(3))
            viewers = [pool.submit(cache.get, KEY, loader) for _ in range(11)]
            release.set()
            results = [owner.result()] + [f.result() for f in viewers]
        loader.assert_called_once()
        results[0].data["scores"][0] = 999
        self.assertEqual(cache.get(KEY, loader).data["scores"], [1, 2])

    def test_ttl_stale_failure_cooldown_and_max_age(self):
        clock = Mock(return_value=100)
        cache = LiveSnapshotCache(ttl=10, max_age=30, retry_delay=20, clock=clock)
        loader = Mock(side_effect=[{"score": 5}, TimeoutError("private detail"), {"score": 6}])
        cache.get(KEY, loader)
        clock.return_value = 110
        result = cache.get(KEY, loader)
        self.assertTrue(result.is_stale)
        self.assertEqual(result.age_seconds, 10)
        self.assertEqual(result.refresh_error_type, "TimeoutError")
        cache.get(KEY, loader)
        self.assertEqual(loader.call_count, 2)
        clock.return_value = 131
        self.assertEqual(cache.get(KEY, loader).data, {"score": 6})

    def test_too_old_data_is_not_served_or_retried_during_cooldown(self):
        clock = Mock(return_value=0)
        cache = LiveSnapshotCache(ttl=5, max_age=10, retry_delay=20, clock=clock)
        cache.get(KEY, lambda: {"score": 1})
        clock.return_value = 11
        loader = Mock(side_effect=RuntimeError("secret"))
        for _ in range(2):
            with self.assertRaises(SnapshotUnavailable):
                cache.get(KEY, loader)
        loader.assert_called_once()

    def test_context_isolation_and_lru_eviction(self):
        cache = LiveSnapshotCache(max_entries=2)
        loader = Mock(return_value={"score": 1})
        cache.get(KEY, loader)
        cache.get(replace(KEY, season_type="Pre Season"), loader)
        cache.get(replace(KEY, provider="nba"), loader)
        cache.get(KEY, loader)
        self.assertEqual(loader.call_count, 4)

    def test_oversize_and_non_json_values_fail_without_poisoning(self):
        for payload in ({"value": "x" * 100}, {"value": float("nan")}, []):
            with self.subTest(payload=type(payload).__name__):
                cache = LiveSnapshotCache(max_payload_bytes=30)
                with self.assertRaises(SnapshotUnavailable):
                    cache.get(KEY, lambda: payload)

    def test_waiter_timeout_serves_only_bounded_stale_data(self):
        clock = Mock(return_value=0)
        cache = LiveSnapshotCache(ttl=5, max_age=20, wait_timeout=0.01, clock=clock)
        cache.get(KEY, lambda: {"score": 1})
        clock.return_value = 6
        entered, release = Event(), Event()
        def load():
            entered.set()
            self.assertTrue(release.wait(3))
            return {"score": 2}
        with ThreadPoolExecutor(max_workers=1) as pool:
            owner = pool.submit(cache.get, KEY, load)
            self.assertTrue(entered.wait(3))
            try:
                result = cache.get(KEY, Mock(side_effect=AssertionError("Duplicate refresh")))
                self.assertTrue(result.is_stale)
                self.assertEqual(result.refresh_error_type, "RefreshInProgress")
                self.assertEqual(result.data, {"score": 1})
            finally:
                release.set()
            self.assertEqual(owner.result().data, {"score": 2})

    def test_active_refreshes_are_not_evicted_to_exceed_capacity(self):
        cache = LiveSnapshotCache(max_entries=1)
        entered, release = Event(), Event()
        def load():
            entered.set()
            self.assertTrue(release.wait(3))
            return {}
        with ThreadPoolExecutor(max_workers=1) as pool:
            owner = pool.submit(cache.get, KEY, load)
            self.assertTrue(entered.wait(3))
            try:
                with self.assertRaisesRegex(SnapshotUnavailable, "capacity"):
                    cache.get(replace(KEY, game_id="0022600002"), Mock())
            finally:
                release.set()
            owner.result()

    def test_cold_failure_has_a_shared_retry_cooldown(self):
        cache = LiveSnapshotCache()
        loader = Mock(side_effect=TimeoutError())
        for _ in range(3):
            with self.assertRaises(SnapshotUnavailable):
                cache.get(KEY, loader)
        loader.assert_called_once()
