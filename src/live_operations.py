"""Read-only, sanitized operations status for the owner beta and command line."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import os

from daily_live_policy import active_games, validate_daily_manifest
from live_artifacts import read_json
from season_config import CURRENT_SEASON


def operations_status(root, environ=None, now=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    environ = os.environ if environ is None else environ
    report = dict(release='owner-beta-daily-v1', checkedAt=now.isoformat(),
                  activeGameIds=list(active_games(root,environ,now)), preparation='unavailable',
                  scope='offline-artifact-health-not-provider-uptime-or-model-readiness')
    try:
        directory = root/'results/live_context'
        context = read_json(directory/f'{CURRENT_SEASON}_day_context_v1.json')
        bundle = read_json(directory/f'{CURRENT_SEASON}_daily_live_v1.json')
        ids = validate_daily_manifest(bundle,context)
        expires = datetime.fromisoformat(bundle['expiresAt'])
        issued = datetime.fromisoformat(bundle['issuedAt'])
        report.update(gameDate=bundle['gameDate'],preparedAt=issued.isoformat(),expiresAt=expires.isoformat(),
                      preparedGames=len(ids),deferredGames=bundle['deferredGames'],
                      rosterTeamsUnavailable=bundle['rosterTeamsUnavailable'],pendingIdentities=bundle['pendingIdentities'])
        report['preparation'] = ('expired' if not issued <= now < expires else
                                 'degraded' if bundle['rosterTeamsUnavailable'] or bundle['pendingIdentities']
                                 or any(g['status']!='inspected' for g in bundle['summaryInspections']) else 'prepared')
    except (OSError,ValueError,KeyError,TypeError,IndexError,OverflowError):
        pass
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = operations_status(args.root)
    print(json.dumps(report,indent=2))
    return 0 if report['preparation']=='prepared' else 1


if __name__ == '__main__':
    raise SystemExit(main())
