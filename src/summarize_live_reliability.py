"""Summarize operator observations, never infer uptime or approve a release."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import statistics


def summarize(lines):
    games = {}
    rejected = 0
    for line in lines:
        if len(line) > 16_384:
            rejected += 1
            continue
        kind = next((k for k in ('COURTVISION_SCORE_COHERENCE ', 'COURTVISION_LIVE_STATE ') if k in line), None)
        if kind is None:
            continue
        try:
            row = json.loads(line.split(kind, 1)[1])
            game_id = row['gameId']
            if not isinstance(game_id, str) or not re.fullmatch(r'002\d{7}', game_id):
                raise ValueError('Invalid public game ID')
            if game_id not in games and len(games) >= 128:
                raise ValueError('Game capacity exceeded')
            if kind.startswith('COURTVISION_SCORE'):
                if row['event'] not in ('coherent', 'mismatch', 'reconciled'):
                    raise ValueError('Unknown event')
                duration = row.get('observedMismatchSeconds')
                if row['event'] == 'reconciled' and (type(duration) not in (int, float)
                        or not math.isfinite(duration) or not 0 <= duration <= 86400):
                    raise ValueError('Invalid observed span')
            else:
                if row['state'] not in ('scheduled', 'unavailable', 'paused', 'stale_snapshot',
                        'possibly_stalled', 'progress_unknown', 'validated_snapshot'):
                    raise ValueError('Unknown presentation state')
                if type(row['samples']) is not int or not 1 <= row['samples'] <= 1_000_000:
                    raise ValueError('Invalid sample count')
            game = games.setdefault(game_id, dict(spans=[], states=Counter(), mismatchEvents=0, reconciliations=0))
            if kind.startswith('COURTVISION_SCORE'):
                if row['event'] == 'mismatch': game['mismatchEvents'] += 1
                if row['event'] == 'reconciled':
                    game['reconciliations'] += 1
                    if len(game['spans']) < 10000: game['spans'].append(float(duration))
            else:
                game['states'][row['state']] += row['samples']
        except (KeyError, ValueError, TypeError):
            rejected += 1
    result = []
    for game_id, game in sorted(games.items()):
        spans = sorted(game['spans'])
        result.append(dict(gameId=game_id, observedReconciliations=game['reconciliations'],
            observedSpanSamples=len(spans), mismatchLogEvents=game['mismatchEvents'],
            medianObservedSpanSeconds=statistics.median(spans) if spans else None,
            p95ObservedSpanSeconds=spans[math.ceil(.95*len(spans))-1] if spans else None,
            presentationSamples=dict(game['states'])))
    return dict(games=result, rejectedRecords=rejected, releaseApproval=False,
        scope='Observed log records only; not provider latency, time-weighted uptime or a full-game certificate. '
              'Partial exports, duplicated lines, process resets and bounded sampling affect results.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    if args.log.stat().st_size > 50_000_000:
        parser.error('Use an operator log export under 50 MB')
    with args.log.open() as source:
        print(json.dumps(summarize(source), indent=2))


if __name__ == '__main__': main()
