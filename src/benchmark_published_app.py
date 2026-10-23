"""Bounded local UI timings. Not hosted cold-start, network, or load measurements."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def benchmark(repeats=3):
    if not 1 <= repeats <= 5:
        raise ValueError("Use 1–5 warm reruns per view")
    started = time.perf_counter()
    # Matplotlib's initial font discovery may inspect system fonts via a process.
    # Initialize before forbidding all subprocesses in the actual app checks.
    import matplotlib.pyplot  # noqa: F401
    from streamlit.testing.v1 import AppTest
    from season_config import CURRENT_SEASON

    report = {"measuredAt": datetime.now(timezone.utc).isoformat(),
              "python": platform.python_version(), "platform": platform.platform(),
              "scope": "Local AppTest execution only; excludes browser, network and hosted provisioning",
              "warmRerunsPerView": repeats, "views": {}}

    def render(action):
        tick = time.perf_counter()
        action()
        if app.exception or app.error:
            raise RuntimeError(f"App failed during benchmark: {app.exception or app.error}")
        return round(time.perf_counter() - tick, 4)

    with patch.dict(os.environ, {"COURTVISION_CLOUD_READY": "1", "COURTVISION_DEPLOYMENT_PROFILE": "published"}), \
         patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected feed request")) as network, \
         patch("subprocess.Popen", side_effect=AssertionError("Unexpected background process")) as workers:
        app = AppTest.from_file(str(ROOT / "cloud/app.py"), default_timeout=90)
        report["firstRenderSeconds"] = render(app.run)
        report["startupThroughFirstRenderSeconds"] = round(time.perf_counter() - started, 4)
        for view in ("Teams", "Players", "Player Career", "Replay Pilot"):
            first = render(lambda: app.sidebar.radio(key="courtvision_season_intelligence_view").set_value(view).run())
            samples = [render(app.run) for _ in range(repeats)]
            report["views"][view] = {"firstSelectionSeconds": first, "warmRerunSeconds": samples,
                                    "warmMedianSeconds": round(statistics.median(samples), 4)}
        report.update(feedRequests=network.call_count, backgroundProcesses=workers.call_count,
                      season=CURRENT_SEASON, replayGames=4)
    # ru_maxrss is bytes on macOS, kilobytes on Linux. This is process high-water
    # usage for the whole benchmark, NOT cloud memory consumption or per-view RSS.
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["localProcessPeakMiB"] = round(peak / (1024 ** 2 if platform.system() == "Darwin" else 1024), 1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    report = benchmark(args.repeats)
    output = ROOT / "results/.runtime/performance/published-ui.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(output)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
