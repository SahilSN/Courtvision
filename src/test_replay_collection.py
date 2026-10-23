import json
from pathlib import Path
import tempfile
import unittest

from published_replay import PILOT_PATH
from replay_collection import GAME_IDS, clock_label, final_label, load_collection


class ReplayCollectionTest(unittest.TestCase):
    def test_curated_collection_has_four_distinct_complete_games(self):
        collection = load_collection()
        self.assertEqual(tuple(collection), GAME_IDS)
        self.assertEqual(len(collection), 4)
        self.assertEqual(len({d["date"] for d, _ in collection.values()}), 4)
        self.assertEqual({int(t.period.max()) for _, t in collection.values()}, {4, 6})

    def test_clock_and_overtime_labels(self):
        self.assertEqual(clock_label("PT00M05.30S"), "0:05")
        self.assertEqual(clock_label("PT12M00.00S"), "12:00")
        self.assertEqual(clock_label("unknown"), "unknown")
        self.assertEqual(final_label(4), "Final")
        self.assertEqual(final_label(5), "Final / 1OT")
        self.assertEqual(final_label(6), "Final / 2OT")

    def test_collection_rejects_wrong_identity_and_missing_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for game_id in GAME_IDS:
                (root / f"{game_id}.json").write_bytes((PILOT_PATH.parent / f"{game_id}.json").read_bytes())
            target = root / f"{GAME_IDS[0]}.json"
            original = json.loads(target.read_text())
            for defect in ("identity", "panel", "nonfinite"):
                data = json.loads(json.dumps(original))
                if defect == "identity":
                    data["gameId"] = "../../other"
                elif defect == "panel":
                    data["playerImpact"] = []
                else:
                    data["timeline"][0]["elapsedGameTime"] = float("inf")
                target.write_text(json.dumps(data))
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    load_collection(root)
