"""Manual, bounded ESPN access probe. Does not enable Live or write datasets."""

import argparse
from datetime import date, datetime, timezone
import json
import re
import ssl
import time
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
MAX_BYTES = 2_000_000


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def fetch_json(url, headers=None):
    started = time.perf_counter()
    try:
        import certifi
        context = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        context = ssl.create_default_context()
    opener = build_opener(NoRedirects(), HTTPSHandler(context=context))
    request_headers = {"User-Agent": "Courtvision-ReadOnly-Diagnostic/1.0"} if headers is None else headers
    with opener.open(Request(url, headers=request_headers), timeout=5) as response:
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Response exceeds diagnostic size limit")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        return data, {"status": response.status, "bytes": len(raw),
                      "seconds": round(time.perf_counter() - started, 3)}


def probe(day, environment, fetcher=fetch_json):
    day = date.fromisoformat(day).strftime("%Y%m%d")
    report = {"checkedAt": datetime.now(timezone.utc).isoformat(), "environment": environment,
              "scope": "ESPN access only; not live correctness, licensing, concurrency, or hosting readiness",
              "requests": [], "status": "failed"}
    try:
        scoreboard, measurement = fetcher(BASE + "scoreboard?dates=" + day)
        events = scoreboard.get("events")
        if not isinstance(events, list):
            raise ValueError("Missing scoreboard events")
        report["requests"].append({"endpoint": "scoreboard", **measurement, "events": len(events)})
        ids = [str(event.get("id", "")) for event in events if isinstance(event, dict)]
        event_id = next((value for value in ids if re.fullmatch(r"\d+", value)), None)
        if event_id:
            summary, measurement = fetcher(BASE + "summary?event=" + event_id)
            if not isinstance(summary.get("header"), dict):
                raise ValueError("Missing summary header")
            report["requests"].append({"endpoint": "summary", **measurement,
                "plays": len(summary.get("plays") or []), "hasBoxScore": isinstance(summary.get("boxscore"), dict)})
        report["status"] = "access_verified" if event_id else "scoreboard_only_no_games"
    except Exception as error:
        report["errorType"] = type(error).__name__
        if getattr(error, "reason", None) is not None:
            report["reasonType"] = type(error.reason).__name__
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--environment", required=True, choices=["mac-local", "github-runner", "community-cloud"])
    args = parser.parse_args()
    result = probe(args.date, args.environment)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["status"] == "failed" else 0)
