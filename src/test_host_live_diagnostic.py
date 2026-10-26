from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from host_live_diagnostic import run_requested_probe


class HostDiagnosticTest(unittest.TestCase):
    def test_pipeline_dispatch_is_explicit_and_unknown_kind_refused(self):
        from unittest.mock import patch
        now=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=self.request(root,now)
            request=json.loads(path.read_text());request['kind']='unknown';path.write_text(json.dumps(request))
            runner=Mock()
            self.assertIsNone(run_requested_probe(path,root/'runtime',now,runner))
            runner.assert_not_called()
            request['kind']='pipeline';path.write_text(json.dumps(request))
            with patch('host_pipeline_probe.probe_pipeline',return_value={'status':'pipeline_baseline_passed'}) as pipeline:
                result=run_requested_probe(path,root/'runtime',now)
            self.assertEqual(result['status'],'pipeline_baseline_passed')
            pipeline.assert_called_once()

    def request(self, root, now):
        path = root / "request.json"
        path.write_text(json.dumps({"requestId": "test-probe", "issuedAt": now.isoformat(),
            "expiresAt": (now + timedelta(minutes=10)).isoformat(), "date": "2026-10-23"}))
        return path

    def test_concurrent_viewers_share_one_attempt(self):
        now = datetime.now(timezone.utc)
        runner = Mock(return_value={"status": "access_verified"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.request(root, now)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(lambda _: run_requested_probe(path, root / "runtime", now, runner), range(16)))
            self.assertEqual(sum(r is not None for r in results), 1)
            runner.assert_called_once_with("2026-10-23", "community-cloud")

    def test_missing_expired_and_future_requests_do_not_run(self):
        now = datetime.now(timezone.utc)
        runner = Mock()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(run_requested_probe(root / "missing", root / "runtime", now, runner))
            path = self.request(root, now)
            for instant in (now - timedelta(seconds=1), now + timedelta(minutes=11)):
                self.assertIsNone(run_requested_probe(path, root / "runtime", instant, runner))
            runner.assert_not_called()

    def test_failed_attempt_is_not_retried(self):
        now = datetime.now(timezone.utc)
        runner = Mock(side_effect=TimeoutError("private error detail"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self.request(root, now)
            first = run_requested_probe(path, root / "runtime", now, runner)
            self.assertEqual(first["errorType"], "TimeoutError")
            self.assertNotIn("private", str(first))
            self.assertIsNone(run_requested_probe(path, root / "runtime", now, runner))
            runner.assert_called_once()
