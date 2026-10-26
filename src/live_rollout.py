"""Default-off, short-lived hosted rollout policy. Not authentication."""

from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from season_config import CURRENT_SEASON


def allowed_games(path, environ, now=None):
    # Two independent operator gates: deployment environment AND reviewed file.
    if environ.get('COURTVISION_ENABLE_LIVE_BETA') != '1' or environ.get('COURTVISION_DISABLE_LIVE_BETA') == '1':
        return ()
    now=now or datetime.now(timezone.utc)
    try:
        config=json.loads(Path(path).read_text())
        issued=datetime.fromisoformat(config['issuedAt'])
        expires=datetime.fromisoformat(config['expiresAt'])
        games=config['gameIds']
        if (type(config['schemaVersion']) is not int or config['schemaVersion']!=1 or config['enabled'] is not True
                or config['season']!=CURRENT_SEASON or config['seasonType']!='Regular Season'
                or issued.tzinfo is None or expires.tzinfo is None or not issued<=now<expires
                or not 0<(expires-issued).total_seconds()<=86400
                or config['gameDate']!=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                or not isinstance(games,list) or not 1<=len(games)<=2
                or any(not isinstance(g,str) or len(g)!=10 or not g.isdigit() or not g.startswith('002'+CURRENT_SEASON[2:4]) for g in games)
                or len(set(games))!=len(games)):
            return ()
        return tuple(games)
    except (OSError,ValueError,KeyError,TypeError,OverflowError):
        return ()
