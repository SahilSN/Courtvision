"""Exact, season/team-scoped additions verified against official NBA sources.

Reviewed October26,2026 via BoxScoreTraditionalV3 or official NBA profiles;
source game IDs/profile URLs retained for audit. No fuzzy names or guessed IDs.
"""
from functools import lru_cache
from nba_api.stats.static import players
from espn_live import normalize_name

REVIEWED = (
    ('2026-27',1610612762,'Darryn Peterson',1643408,'0022600112'),
    ('2026-27',1610612751,'Chaney Johnson',1643052,'0022600113'),
    ('2026-27',1610612751,'Joshua Jefferson',1643538,'0022600113'),
    ('2026-27',1610612766,'Christian Anderson',1643515,'https://www.nba.com/player/1643515/christian-anderson'),
    ('2026-27',1610612739,'Meleek Thomas',1643509,'https://www.nba.com/player/1643509/meleek-thomas/profile'),
)


@lru_cache(maxsize=1)
def _static_index():
    index={}
    for person in players.get_players():
        index.setdefault(normalize_name(person['full_name']),set()).add(int(person['id']))
    return index


def candidates(name,season,team_id):
    name=normalize_name(name)
    result=set(_static_index().get(name,()))
    result.update(person for s,t,n,person,_ in REVIEWED if s==season and t==team_id and normalize_name(n)==name)
    return result
