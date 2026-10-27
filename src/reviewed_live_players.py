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
    ('2026-27',1610612741,'Caleb Wilson',1643410,'https://www.nba.com/player/1643410/caleb-wilson'),
    ('2026-27',1610612741,'Tobe Awaka',1643591,'https://www.nba.com/player/1643591/tobe-awaka'),
    ('2026-27',1610612741,'Dailyn Swain',1643517,'https://www.nba.com/player/1643517/dailyn-swain/profile'),
    ('2026-27',1610612741,'Jaylin Sellers',1643637,'https://stats.nba.com/stats/commonteamroster?TeamID=1610612741&Season=2026-27'),
    ('2026-27',1610612742,'Morez Johnson Jr.',1643516,'https://www.nba.com/player/1643516/morez-johnson'),
    ('2026-27',1610612742,'Sergio de Larrea',1643547,'https://www.nba.com/player/1643547'),
    ('2026-27',1610612749,'Nate Ament',1643417,'https://www.nba.com/player/1643417/nate-ament'),
    ('2026-27',1610612749,'Brayden Burries',1643415,'https://www.nba.com/player/1643415'),
    ('2026-27',1610612738,'Chris Cenac Jr.',1643416,'https://www.nba.com/player/1643416/chris-cenac-jr'),
    ('2026-27',1610612737,'Kingston Flemings',1643412,'https://www.nba.com/player/1643412/kingston-flemings'),
    ('2026-27',1610612763,'Cameron Boozer',1643409,'https://www.nba.com/player/1643409/cameron-boozer'),
    ('2026-27',1610612744,'Yaxel Lendeborg',1642865,'https://www.nba.com/player/1642865/yaxel-lendeborg'),
    ('2026-27',1610612744,'Brandon Williams',1630314,'https://www.nba.com/player/1630314/brandon-williams'),
    ('2026-27',1610612743,'Bryce Hopkins',1643624,'https://www.nba.com/player/1643624/bryce-hopkins/bio'),
    ('2026-27',1610612743,'Trevon Brazile',1642350,'https://www.nba.com/player/1642350/trevon-brazile'),
)


@lru_cache(maxsize=1)
def _static_index():
    index={}
    for person in players.get_players():
        index.setdefault(normalize_name(person['full_name']),set()).add(int(person['id']))
    return index


def candidates(name,season,team_id):
    name=normalize_name(name)
    reviewed={person for s,t,n,person,_ in REVIEWED if s==season and t==team_id and normalize_name(n)==name}
    # An exact reviewed season/team identity disambiguates names shared with
    # retired players (Brandon Williams). Conflicting reviewed IDs stay ambiguous.
    return reviewed or set(_static_index().get(name,()))
