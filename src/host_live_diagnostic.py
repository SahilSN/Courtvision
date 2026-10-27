"""Operator-deployed, expiring, once-per-container diagnostic; logs only, no UI."""

from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import runpy

from probe_live_access import probe


def run_requested_probe(request_path, runtime, now=None, runner=None):
    now = now or datetime.now(timezone.utc)
    try:
        request = json.loads(Path(request_path).read_text())
        request_id = request["requestId"]
        issued = datetime.fromisoformat(request["issuedAt"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(request["expiresAt"].replace("Z", "+00:00"))
        day = date.fromisoformat(request["date"]).isoformat()
        kind=request.get('kind','access')
        if kind not in ('access','pipeline','current'):
            return None
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
        if runner is None:
            if kind == 'current':
                runner=runpy.run_path(str(Path(__file__).with_name('host_current_probe.py')))['probe_current']
            elif kind == 'pipeline':
                runner=runpy.run_path(str(Path(__file__).with_name('host_pipeline_probe.py')))['probe_pipeline']
            else:
                runner=probe
        report = runner(day, "community-cloud")
    except Exception as error:
        report = {"status": "failed", "errorType": type(error).__name__}
    report = {**report, "requestId": request_id}
    print("COURTVISION_HOST_PROBE " + json.dumps(report), flush=True)
    return report
