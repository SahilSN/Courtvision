"""Operator-deployed, expiring, once-per-container diagnostic; logs only, no UI."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re

from probe_live_access import probe


def run_requested_probe(request_path, runtime, now=None, runner=probe):
    now = now or datetime.now(timezone.utc)
    try:
        request = json.loads(Path(request_path).read_text())
        request_id = request["requestId"]
        issued = datetime.fromisoformat(request["issuedAt"])
        expires = datetime.fromisoformat(request["expiresAt"])
        day = date.fromisoformat(request["date"]).isoformat()
        if (not re.fullmatch(r"[a-z0-9-]{1,64}", request_id) or issued.tzinfo is None or expires.tzinfo is None
                or not 0 < (expires - issued).total_seconds() <= 900 or not issued <= now < expires):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    runtime = Path(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation prevents duplicate requests across simultaneous viewers.
        # Claim first: an interrupted attempt must not retry on every rerun.
        with (runtime / f"{request_id}.claim").open("x") as claim:
            claim.write(now.isoformat())
    except FileExistsError:
        return None
    try:
        report = runner(day, "community-cloud")
    except Exception as error:
        report = {"status": "failed", "errorType": type(error).__name__}
    report = {**report, "requestId": request_id}
    print("COURTVISION_HOST_PROBE " + json.dumps(report), flush=True)
    return report
