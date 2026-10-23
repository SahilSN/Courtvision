import unittest
from unittest.mock import Mock

from probe_live_access import probe


class LiveAccessProbeTest(unittest.TestCase):
    def test_at_most_two_read_only_requests(self):
        fetch = Mock(side_effect=[({"events": [{"id": "123"}]}, {"status": 200}),
                                  ({"header": {}, "plays": []}, {"status": 200})])
        report = probe("2026-10-23", "mac-local", fetch)
        self.assertEqual(report["status"], "access_verified")
        self.assertEqual(fetch.call_count, 2)

    def test_failure_does_not_retry_or_expose_error_details(self):
        fetch = Mock(side_effect=TimeoutError("sensitive diagnostic detail"))
        report = probe("2026-10-23", "github-runner", fetch)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["errorType"], "TimeoutError")
        self.assertNotIn("sensitive", str(report))
        fetch.assert_called_once()

    def test_empty_schedule_is_not_full_verification(self):
        fetch = Mock(return_value=({"events": []}, {"status": 200}))
        self.assertEqual(probe("2026-10-23", "mac-local", fetch)["status"], "scoreboard_only_no_games")
        fetch.assert_called_once()
