"""Observe real worker checkpoints; never start inference or alter the queue."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

from live_artifacts import read_json, write_json


def measure(root, label, samples=3, timeout=900):
    if not 1 <= samples <= 10 or label not in ('low', 'normal'):
        raise ValueError('Choose low/normal and 1–10 samples')
    runtime = Path(root) / 'results/.runtime/replay-expansion'
    output = runtime / 'priority-comparison' / f'{label}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json'
    records, active = [], None
    started = time.monotonic()
    while len(records) < samples and time.monotonic() - started < timeout:
        state = read_json(runtime / 'state.json')
        if active and state.get('heartbeatAt') != active['start']:
            end = state.get('health', {}).get('checkedAt')
            if end and end > active['start']:
                elapsed = (datetime.fromisoformat(end) - datetime.fromisoformat(active['start'])).total_seconds()
                prepared = sum(state['games'].get(gid, {}).get('status') == 'prepared' for gid in active['ids'])
                record = {**active, 'end': end, 'seconds': elapsed, 'prepared': prepared,
                          'gamesPerMinute': prepared * 60 / elapsed if elapsed > 0 else 0}
                records.append(record)
                write_json(output, {'label': label, 'samples': records})
                print(record, flush=True)
                active = None
        if state.get('workerPhase') == 'processing' and active is None:
            active = {'start': state['heartbeatAt'], 'ids': state['batchGameIds'],
                      'season': state['batchSeason']}
        time.sleep(.5)
    print(f'Saved {len(records)} samples: {output}', flush=True)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--label', choices=['low', 'normal'], required=True)
    parser.add_argument('--samples', type=int, default=3)
    args = parser.parse_args()
    measure(args.root, args.label, args.samples)
