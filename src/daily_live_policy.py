"""Offline, expiring owner-beta policy. No feed calls or publication here."""

from datetime import datetime, timezone
from pathlib import Path

from live_artifacts import read_json, digest
from live_game_date import eligible_game_date
from season_config import CURRENT_SEASON


def validate_daily_manifest(bundle, context):
    # The full per-game reader is called by the worker/policy after this shape
    # check; digest prevents a partially published context/manifest combination.
    if (type(bundle['schemaVersion']) is not int or bundle['schemaVersion'] != 1
            or bundle['season'] != CURRENT_SEASON or bundle['seasonType'] != 'Regular Season'
            or bundle['gameDate'] != context['gameDate']
            or type(context['schemaVersion']) is not int or context['schemaVersion'] != 1
            or context['season'] != CURRENT_SEASON or context['seasonType'] != 'Regular Season'
            or bundle['contextDigest'] != digest(context)):
        raise ValueError('Daily Live manifest/context disagree')
    issued, expires = (datetime.fromisoformat(bundle[k]) for k in ('issuedAt','expiresAt'))
    if issued.tzinfo is None or expires.tzinfo is None or not 0 < (expires-issued).total_seconds() <= 86400:
        raise ValueError('Invalid daily Live lifetime')
    ids = bundle['gameIds']
    if (not isinstance(ids, list) or len(ids) > 4 or len(set(ids)) != len(ids)
            or any(not isinstance(g, str) or len(g) != 10 or not g.isdigit()
                   or not g.startswith('002'+CURRENT_SEASON[2:4]) for g in ids)):
        raise ValueError('Invalid bounded daily slate')
    if any(sum(g['gameId'] == game_id for g in context['games']) != 1 for game_id in ids):
        raise ValueError('Unknown or duplicate daily game')
    for key,limit in [('scheduledGames',15),('deferredGames',15),('rosterTeamsVerified',8),
                      ('rosterTeamsUnavailable',8),('pendingIdentities',240)]:
        if type(bundle[key]) is not int or not 0 <= bundle[key] <= limit:
            raise ValueError('Invalid preparation counters')
    inspections = bundle['summaryInspections']
    if (not isinstance(inspections,list) or len(inspections) != len(ids)
            or {g['gameId'] for g in inspections} != set(ids)
            or any(g['status'] not in ('inspected','unavailable') for g in inspections)):
        raise ValueError('Invalid preparation observations')
    return tuple(ids)


def allowed_daily_games(root, environ, now=None):
    from daily_live_context import read_day_context
    root = Path(root)
    if environ.get('COURTVISION_ENABLE_LIVE_BETA') != '1' or environ.get('COURTVISION_DISABLE_LIVE_BETA') == '1':
        return ()
    now = now or datetime.now(timezone.utc)
    try:
        policy = read_json(root/'cloud/live_daily_policy.json')
        start, end = (datetime.fromisoformat(policy[k]) for k in ('issuedAt','expiresAt'))
        if (type(policy['schemaVersion']) is not int or policy['schemaVersion'] != 1
                or policy['enabled'] is not True or policy['season'] != CURRENT_SEASON
                or policy['seasonType'] != 'Regular Season'
                or type(policy['maxGames']) is not int or not 1 <= policy['maxGames'] <= 4
                or now.tzinfo is None or start.tzinfo is None or end.tzinfo is None
                or not start <= now < end or not 0 < (end-start).total_seconds() <= 7*86400):
            return ()
        directory = root/'results/live_context'
        context_path = directory/f'{CURRENT_SEASON}_day_context_v1.json'
        context = read_json(context_path)
        bundle = read_json(directory/f'{CURRENT_SEASON}_daily_live_v1.json')
        ids = validate_daily_manifest(bundle, context)
        issued, expires = (datetime.fromisoformat(bundle[k]) for k in ('issuedAt','expiresAt'))
        if (not issued <= now < expires or not eligible_game_date(bundle['gameDate'], now)
                or len(ids) > policy['maxGames']):
            return ()
        for game_id in ids:
            game, = [g for g in context['games'] if g['gameId'] == game_id]
            read_day_context(context_path, game)
        return ids
    except (OSError, KeyError, TypeError, ValueError, IndexError, OverflowError):
        return ()


def active_games(root, environ, now=None):
    """A valid manual window wins. Disabled/corrupt manual files fail closed."""
    from live_rollout import allowed_games
    root = Path(root)
    manual = root/'cloud/live_rollout.json'
    if manual.exists():
        try:
            config = read_json(manual)
            if config.get('enabled') is not True:
                return ()
            selected = allowed_games(manual, environ, now)
            if selected:
                return selected
            # Only an expired manual window can hand over to daily operation;
            # malformed, future or otherwise invalid windows must not broaden.
            issued = datetime.fromisoformat(config['issuedAt'])
            expires = datetime.fromisoformat(config['expiresAt'])
            instant = now or datetime.now(timezone.utc)
            if (expires.tzinfo is None or issued.tzinfo is None or instant < expires
                    or not allowed_games(manual,environ,issued)):
                return ()
        except (OSError, KeyError, ValueError, TypeError, OverflowError):
            return ()
    return allowed_daily_games(root, environ, now)
