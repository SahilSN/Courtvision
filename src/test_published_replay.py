import copy
import json
from pathlib import Path
import tempfile
import unittest

from published_replay import load_replay


class PublishedReplayTest(unittest.TestCase):
    def test_pilot_reconciles_and_contains_full_game_views(self):
        data, timeline = load_replay()
        self.assertEqual((data["home"]["score"], data["away"]["score"]), (125, 124))
        self.assertEqual(int(timeline.period.max()), 6)
        for field in ("turningPoints", "playerImpact", "boxScore"):
            self.assertTrue(data[field])

    def test_corrupt_artifacts_fail_closed(self):
        original, _ = load_replay()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for defect in ("probability", "score", "order", "version"):
                data = copy.deepcopy(original)
                if defect == "probability":
                    data["timeline"][0]["winProbability"] = 2
                elif defect == "score":
                    data["home"]["score"] += 1
                elif defect == "order":
                    data["timeline"].reverse()
                else:
                    data["schemaVersion"] = 999
                path.write_text(json.dumps(data))
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    load_replay(path)
