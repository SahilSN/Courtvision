import fcntl
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from player_rating import build_player_ratings
from publish_historical_checkpoint import historical_season, publish_historical, validate_checkpoint
from run_nightly_intelligence import git
from test_player_rating import make_appearance


class HistoricalCheckpointTest(unittest.TestCase):
    def setUp(self):
        self.games = pd.DataFrame([make_appearance(1, "Player", i, 0.3) for i in (1, 2)])
        self.expected = set(self.games.gameId)

    def test_mismatched_csv_pair_is_rejected(self):
        with self.assertRaises(AssertionError):
            validate_checkpoint("2025-26", self.games,
                build_player_ratings(self.games.iloc[:1]), self.expected)

    def test_regression_or_changed_published_appearance_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "remove"):
            validate_checkpoint("2025-26", self.games.iloc[:1],
                build_player_ratings(self.games.iloc[:1]), self.expected, self.games)
        changed = self.games.copy()
        changed.loc[0, "minutes"] = 31
        with self.assertRaises(AssertionError):
            validate_checkpoint("2025-26", changed, build_player_ratings(changed), self.expected, self.games)

    def test_current_season_and_paths_are_rejected(self):
        for season in ("2026-27", "2027-28", "2025-28", "../2025-26"):
            with self.subTest(season=season), self.assertRaises(ValueError):
                historical_season(season)

    def test_isolated_publication_preserves_source_and_only_pushes_the_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            remote, source = base / "remote.git", base / "source"
            source.mkdir()
            git(base, "init", "--bare", "--initial-branch=main", str(remote))
            git(source, "init", "--initial-branch=main")
            git(source, "config", "user.name", "Test")
            git(source, "config", "user.email", "test@example.com")
            player = source / "results/player_intelligence"
            history = source / "results/season_intelligence"
            player.mkdir(parents=True)
            history.mkdir(parents=True)
            (source / "README.md").write_text("original\n")
            self.games[["gameId"]].to_csv(history / "2025-26_team_rating_games_v1.csv", index=False)
            self.games.iloc[:1].to_csv(player / "2025-26_player_game_v1.csv", index=False)
            build_player_ratings(self.games.iloc[:1]).to_csv(player / "2025-26_player_ratings_v1.csv", index=False)
            git(source, "add", ".")
            git(source, "commit", "-m", "initial")
            git(source, "remote", "add", "origin", str(remote))
            git(source, "push", "-u", "origin", "main")
            (source / "README.md").write_text("user staged changes\n")
            git(source, "add", "README.md")
            original_index = git(source, "diff", "--cached", "--binary").stdout
            original_head = git(source, "rev-parse", "HEAD").stdout
            self.games.to_csv(player / "2025-26_player_game_v1.csv", index=False)
            build_player_ratings(self.games).to_csv(player / "2025-26_player_ratings_v1.csv", index=False)
            publish_historical(["2025-26"], source)
            self.assertEqual(git(source, "diff", "--cached", "--binary").stdout, original_index)
            self.assertEqual(git(source, "rev-parse", "HEAD").stdout, original_head)
            changed = git(base, "--git-dir", str(remote), "diff-tree", "--no-commit-id", "--name-only", "-r", "main").stdout.splitlines()
            self.assertEqual(set(changed), {"results/player_intelligence/2025-26_player_game_v1.csv", "results/player_intelligence/2025-26_player_ratings_v1.csv"})
            self.assertEqual(publish_historical(["2025-26"], source), "No historical checkpoint changes")
            with (player / ".runtime/checkpoint.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):
                    publish_historical(["2025-26"], source)


if __name__ == "__main__":
    unittest.main()
