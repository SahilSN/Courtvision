import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from historical_publication import MilestonePublication
from run_historical_backfill import run_backfill


def coverage(count, expected=1230):
    return {"2025-26": {"processedGames": count, "expectedGames": expected}}


class HistoricalPublicationTest(unittest.TestCase):
    def test_stalled_season_flushes_validated_partial_without_claiming_complete(self):
        publish = Mock(return_value='commit')
        with tempfile.TemporaryDirectory() as directory:
            worker = MilestonePublication(Path(directory) / 'publication.json', 500, publish)
            worker.state['publishedGames'] = {'2025-26': 1039}
            worker.update(coverage(1229), flush_seasons=['2025-26'])
            publish.assert_called_once_with(['2025-26'])
            self.assertEqual(worker.state['publishedGames']['2025-26'], 1229)
            worker.update(coverage(1229), flush_seasons=['2025-26'])
            self.assertEqual(publish.call_count, 1)

    def test_milestones_restart_and_completion(self):
        publish = Mock(return_value="commit")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publication.json"
            worker = MilestonePublication(path, 500, publish)
            self.assertTrue(worker.update(coverage(499)))
            publish.assert_not_called()
            self.assertTrue(worker.update(coverage(510)))
            publish.assert_called_once_with(["2025-26"])
            worker = MilestonePublication(path, 500, publish)
            worker.update(coverage(999))
            self.assertEqual(publish.call_count, 1)
            worker.update(coverage(1010))
            worker.update(coverage(1230))
            worker.update(coverage(1230))
            self.assertEqual(publish.call_count, 3)
            self.assertEqual(worker.state["publishedGames"], {"2025-26": 1230})

    def test_failure_retries_after_cooldown_without_advancing_baseline(self):
        publish = Mock(side_effect=[RuntimeError("network unavailable"), "commit"])
        clock = Mock(return_value=1000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publication.json"
            worker = MilestonePublication(path, 500, publish, clock)
            self.assertFalse(worker.update(coverage(600)))
            self.assertEqual(worker.state["publishedGames"], {})
            worker = MilestonePublication(path, 500, publish, clock)
            self.assertFalse(worker.update(coverage(650)))
            self.assertEqual(publish.call_count, 1)
            clock.return_value = 1900
            self.assertTrue(worker.update(coverage(700)))
            self.assertEqual(worker.state["publishedGames"], {"2025-26": 700})

    def test_several_completed_seasons_publish_together_even_below_threshold(self):
        publish = Mock(return_value="No historical checkpoint changes")
        with tempfile.TemporaryDirectory() as directory:
            worker = MilestonePublication(Path(directory) / "publication.json", 500, publish)
            worker.update({**coverage(10, 10), "2024-25": {"processedGames": 20, "expectedGames": 20}})
            publish.assert_called_once_with(["2025-26", "2024-25"])

    def test_complete_local_data_is_not_reported_complete_when_upload_fails(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("run_historical_backfill.PLAYER_INTELLIGENCE_DIR", directory), \
             patch("run_historical_backfill.progress", return_value=coverage(10, 10)), \
             patch("run_historical_backfill.MilestonePublication") as factory:
            factory.return_value.update.return_value = False
            factory.return_value.state = {"status": "retry_pending"}
            self.assertEqual(run_backfill(["2025-26"], directory,
                             publish_every_games=500, max_rounds=1), 1)
            state = json.loads((Path(directory) / ".runtime/status.json").read_text())
            self.assertEqual(state["status"], "local_complete_publication_pending")

    def test_alternate_output_cannot_accidentally_publish_repository_data(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                run_backfill(["2025-26"], directory, publish_every_games=500)


if __name__ == "__main__":
    unittest.main()
