import pickle
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backfill_player_rating_sample import (
    build_work_plan,
    fetch_and_cache_box_score,
    select_evenly_spaced_games,
)


class PlayerRatingSampleBackfillTest(unittest.TestCase):
    def test_even_sample_is_deterministic_and_includes_endpoints(self):
        games = pd.DataFrame(
            {
                "gameId": [
                    f"0022500{index:03d}"
                    for index in range(10)
                ],
                "gameDate": pd.date_range(
                    "2025-10-21",
                    periods=10,
                ),
            }
        )

        selected = select_evenly_spaced_games(
            games,
            sample_size=4,
        )

        self.assertEqual(
            selected["gameId"].tolist(),
            [
                games.iloc[0]["gameId"],
                games.iloc[3]["gameId"],
                games.iloc[6]["gameId"],
                games.iloc[9]["gameId"],
            ],
        )

    def test_work_plan_recognizes_complete_and_partial_games(self):
        games = pd.DataFrame(
            [
                {
                    "gameId": "0022500001",
                    "gameDate": pd.Timestamp("2025-10-21"),
                },
                {
                    "gameId": "0022500002",
                    "gameDate": pd.Timestamp("2025-10-22"),
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            results = root / "results"
            box_cache = root / "box"
            results.mkdir()
            box_cache.mkdir()

            for suffix in (
                "summary.csv",
                "events.csv",
                "sequences.csv",
            ):
                (
                    results
                    / f"player_wpa_v3_0022500001_{suffix}"
                ).touch()
            (box_cache / "0022500001.pkl").touch()
            (
                results
                / "player_wpa_v3_0022500002_summary.csv"
            ).touch()

            plan = build_work_plan(
                games,
                results_dir=results,
                box_cache_dir=box_cache,
            )

        complete = plan.iloc[0]
        partial = plan.iloc[1]
        self.assertFalse(bool(complete["needsWPA"]))
        self.assertFalse(bool(complete["needsBoxScore"]))
        self.assertTrue(bool(partial["needsWPA"]))
        self.assertTrue(bool(partial["needsBoxScore"]))

    def test_box_score_retry_writes_compatible_cache(self):
        attempts = []

        def fetcher(game_id):
            attempts.append(game_id)
            if len(attempts) == 1:
                raise TimeoutError("temporary failure")
            return {
                "players": pd.DataFrame(),
            }

        with tempfile.TemporaryDirectory() as temporary_directory:
            path = fetch_and_cache_box_score(
                "22500001",
                retries=2,
                retry_delay=0,
                fetcher=fetcher,
                box_cache_dir=temporary_directory,
            )

            self.assertTrue(path.exists())
            self.assertEqual(len(attempts), 2)

            with path.open("rb") as cache_file:
                payload = pickle.load(cache_file)

            self.assertEqual(payload["cache_version"], "v1")
            self.assertEqual(payload["game_id"], "0022500001")
            self.assertIn("players", payload["box_score"])

    def test_box_score_retry_arguments_are_validated(self):
        with self.assertRaisesRegex(
            ValueError,
            "retries must be positive",
        ):
            fetch_and_cache_box_score(
                "0022500001",
                retries=0,
            )

        with self.assertRaisesRegex(
            ValueError,
            "retry_delay cannot be negative",
        ):
            fetch_and_cache_box_score(
                "0022500001",
                retry_delay=-1,
            )


if __name__ == "__main__":
    unittest.main()
