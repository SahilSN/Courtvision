"""Bounded, read-only health summaries. Never publish raw worker errors or logs."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from live_artifacts import read_json
from season_config import CURRENT_SEASON


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('Timezone required')
    return stamp


def intelligence_status(root, now=None):
    """Published refresh evidence, not proof that the Mac is online now."""
    now = now or datetime.now(timezone.utc)
    report = {'checkedAt': now.isoformat(), 'scope': 'published-refresh-evidence', 'pipelines': {}}
    try:
        source = read_json(Path(root)/'results/season_intelligence'/f'{CURRENT_SEASON}_update_status_v1.json')
        if source['season'] != CURRENT_SEASON:
            raise ValueError('Wrong season')
        pipelines = source['pipelines']
    except (OSError, ValueError, KeyError, TypeError):
        pipelines = {}
    for name in ('teams', 'players'):
        item = {'state': 'unavailable', 'action': 'Inspect the Mac nightly status and publication logs.'}
        try:
            saved = pipelines[name]
            checked = timestamp(saved['checkedAt'])
            state = saved['status']
            if state not in ('success', 'partial', 'failed') or checked > now:
                raise ValueError('Invalid refresh evidence')
            processed, completed = saved['processedGames'], saved['completedGames']
            if (type(processed) is not int or processed < 0 or
                    completed is not None and (type(completed) is not int or completed < processed)):
                raise ValueError('Invalid counts')
            through = saved['gamesThrough']
            if through is not None and date.fromisoformat(through) > now.date():
                raise ValueError('Future games')
            if state == 'success' and (completed is None or processed != completed or
                                       saved.get('pendingGameIds') or saved.get('failures') or saved.get('error')):
                raise ValueError('Incomplete success')
            item.update(state='stale' if now-checked > timedelta(hours=36) else state,
                        lastCheckAt=checked.isoformat(), gamesThrough=through,
                        processedGames=processed, completedGames=completed)
            if item['state'] == 'success':
                item['action'] = 'No action required for this published refresh.'
            elif item['state'] == 'partial':
                item['action'] = 'Some completed games are pending. Inspect nightly logs; retain validated data.'
            elif item['state'] == 'failed':
                item['action'] = 'Latest refresh failed. Inspect source availability and retry through the existing nightly job.'
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError):
            pass
        report['pipelines'][name] = item
    return report


def nightly_status(root):
    """Local CLI evidence only; absent on Cloud is not a failed Mac job."""
    try:
        saved = read_json(Path(root)/'results/.runtime/nightly/status.json')
        state = saved['status']
        if state not in ('running', 'success', 'incomplete', 'failed'):
            raise ValueError('Unknown status')
        result = {'state': state, 'startedAt': timestamp(saved['startedAt']).isoformat(),
                  'scope': 'saved-local-attempt-not-worker-liveness'}
        if state != 'running':
            result['finishedAt'] = timestamp(saved['finishedAt']).isoformat()
        result['publication'] = ('recorded' if saved.get('publication') else 'not-recorded')
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {'state': 'unavailable', 'scope': 'saved-local-attempt-not-worker-liveness'}
