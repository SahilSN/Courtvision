"""Read-only, loopback-only progress page for the Mac replay worker."""

from collections import Counter
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from zoneinfo import ZoneInfo

from live_artifacts import read_json
from replay_catalog import read_index


def progress(root):
    root = Path(root)
    runtime = root / 'results/.runtime/replay-expansion'
    state = read_json(runtime / 'state.json')
    entries = read_index(runtime / 'prepared')
    published = state.get('publishedReplayCount')
    if published is None:
        published = len(read_index(root))
    errors = runtime / 'worker_error.json'
    error = read_json(errors) if errors.exists() else {}
    return {
        'prepared': len(entries), 'published': published,
        'awaitingPublication': max(0, len(entries) - published),
        'bySeason': dict(sorted(Counter(e['season'] for e in entries.values()).items(), reverse=True)),
        'blocked': sum(g['status'] == 'blocked' for g in state['games'].values()),
        'attemptsToday': state.get('dailyAttempts', 0),
        'phase': state.get('workerPhase', 'starting'),
        'priority': state.get('executionPriority', 'low'),
        'heartbeatAt': state.get('heartbeatAt', state.get('health', {}).get('checkedAt', '')),
        'batchSeason': state.get('batchSeason', ''), 'batchGameIds': state.get('batchGameIds', []),
        'lastPublishAt': state.get('lastPublishAt', ''),
        'publicationState': state.get('publicationState', 'not_due'),
        'pausedSeasons': ['2024-25'],
        'workerError': error.get('errorType') if error.get('checkedAt', '') > state.get('heartbeatAt', '') else None,
    }


def page(value):
    def local_time(stamp):
        return datetime.fromisoformat(stamp).astimezone(ZoneInfo('America/Los_Angeles')).strftime('%b %d, %I:%M:%S %p PT') if stamp else 'not yet'
    cards = ''.join(f'<section><span>{label}</span><strong>{value[key]:,}</strong></section>'
                    for key, label in [('prepared', 'Prepared locally'), ('published', 'Published'),
                                       ('awaitingPublication', 'Awaiting nightly publish'), ('blocked', 'Blocked attempts')])
    rows = ''.join(f'<tr><td>{escape(season)}</td><td>{count:,}</td></tr>'
                   for season, count in value['bySeason'].items())
    batch = ', '.join(value['batchGameIds']) or 'No active batch'
    phase = value['workerError'] or value['phase'].replace('_', ' ').title()
    return f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="10">
<title>Courtvision · Replay progress</title><style>
body{{background:#0e1117;color:#edf2f7;font:16px system-ui;max-width:960px;margin:48px auto;padding:0 24px}}
h1{{letter-spacing:-1px}}p,span{{color:#a7b4c7;line-height:1.7}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}}
section{{border:1px solid #303845;border-radius:14px;padding:20px}}strong{{display:block;font-size:32px;margin-top:8px;color:#83bff5}}
table{{width:100%;border-collapse:collapse;margin:24px 0}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #303845}}small{{color:#a7b4c7}}
</style></head><body><small>COURTVISION · THIS MAC ONLY</small><h1>Historical replay progress</h1>
<p>{escape(phase)} · unlimited catch-up at {escape(value['priority'])} priority · refreshes every 10 seconds</p>
<div class="cards">{cards}</div><p>Batch: {escape(value['batchSeason'])} · {escape(batch)}<br>
Last worker update: {escape(local_time(value['heartbeatAt']))}<br>Attempts today: {value['attemptsToday']:,} · no daily cap</p>
<h2>Prepared by season</h2><table><tr><th>Season</th><th>Replays</th></tr>{rows}</table>
<p>2024–25 is paused for opening-state repair. Games missing local inputs wait for backfill.
Counts are prepared coverage, not a complete NBA archive.</p>
<p>Publishing: {escape(value['publicationState'])} · last success {escape(local_time(value['lastPublishAt']))}.
Validated batches publish after 1:30 a.m. Pacific, once nightly. The hosted app shows the last published snapshot.</p>
<p>Processing pauses when this Mac sleeps and resumes after waking. No ChatGPT session is needed.</p></body></html>'''


def start_progress_server(root, port=8520):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ('/', '/status'):
                self.send_error(404)
                return
            try:
                value = progress(root)
                payload = (json.dumps(value) if self.path == '/status' else page(value)).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json' if self.path == '/status' else 'text/html; charset=utf-8')
            except (OSError, ValueError, KeyError, TypeError):
                payload = b'Progress is initializing or unavailable. Check the local worker logs.'
                self.send_response(503)
                self.send_header('Content-Type', 'text/plain')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
