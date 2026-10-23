"""Durable, opt-in publication milestones, independent of source retries."""

import json
from pathlib import Path
import time

from publish_historical_checkpoint import publish_historical


class MilestonePublication:
    def __init__(self, path, every_games, publisher=publish_historical, clock=time.time):
        self.path = Path(path)
        self.every_games = every_games
        self.publisher = publisher
        self.clock = clock
        # Corrupt health must not silently reset the publication baseline.
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "publishedGames": {}, "failureCount": 0, "nextRetryAt": None}

    def save(self):
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.state, indent=2) + "\n")
        temporary.replace(self.path)

    def update(self, coverage):
        published = self.state["publishedGames"]
        due = [s for s, c in coverage.items()
               if c["processedGames"] > published.get(s, 0)
               and (c["processedGames"] - published.get(s, 0) >= self.every_games
                    or c["processedGames"] == c["expectedGames"])]
        self.state["pendingSeasons"] = due
        if not due:
            return True
        if self.state.get("nextRetryAt") and self.clock() < self.state["nextRetryAt"]:
            return False
        try:
            result = self.publisher(due)
        except Exception as error:
            self.state.update(status="retry_pending", error=str(error)[:1000],
                              failureCount=self.state["failureCount"] + 1,
                              nextRetryAt=self.clock() + 900)
        else:
            published.update({s: coverage[s]["processedGames"] for s in due})
            self.state.update(status="success", lastSuccessAt=self.clock(),
                              publication=result, nextRetryAt=None, error=None,
                              pendingSeasons=[])
        self.save()
        return not self.state["pendingSeasons"]
