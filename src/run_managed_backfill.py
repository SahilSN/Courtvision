"""LaunchAgent entry point: resumable backfill with bounded, rotating logs."""

import contextlib
import logging
from logging.handlers import RotatingFileHandler

from run_historical_backfill import run_backfill
from run_nightly_intelligence import LogStream
from update_intelligence import ROOT_DIR


SEASONS = ["2025-26", "2024-25", "2023-24", "2022-23", "2021-22", "2020-21", "2019-20"]


def main():
    runtime = ROOT_DIR / "results/player_intelligence/.runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("courtvision.backfill")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(runtime / "backfill.log", maxBytes=2_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    stream = LogStream(logger)
    try:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            return run_backfill(SEASONS, publish_every_games=500)
    except Exception:
        logger.exception("Backfill stopped; launchd will retry")
        return 1
    finally:
        stream.flush()
        logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
