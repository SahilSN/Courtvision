"""Read-only local worker health; never infer Mac liveness from a hosted snapshot."""

import fcntl
import json
from pathlib import Path


def backfill_health(root):
    runtime = Path(root) / "results/player_intelligence/.runtime"
    try:
        state = json.loads((runtime / "status.json").read_text())
        if not isinstance(state, dict):
            raise ValueError("Invalid worker status")
        with (runtime / "runner.lock").open("r") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                active = True
            else:
                active = False
                fcntl.flock(lock, fcntl.LOCK_UN)
    except (OSError, ValueError, TypeError):
        return "Backfill status unavailable. Published coverage is shown below."
    if not active:
        if state.get("status") == "complete":
            return "Historical backfill complete · saved coverage is shown below."
        return "Backfill is not running · saved progress is retained."
    publication = state.get("publication", {})
    if publication.get("status") == "retry_pending":
        return "Backfill running · upload pending; publication will retry automatically."
    if state.get("status") == "waiting":
        return "Backfill waiting for a source retry · saved progress is retained."
    return "Backfill running · validated checkpoints publish at milestones and season completion."
