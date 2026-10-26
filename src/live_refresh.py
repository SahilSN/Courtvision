"""Bounded ESPN pair loader: no discovery fallback or fabricated estimates."""

from datetime import datetime
from zoneinfo import ZoneInfo
from cloud_espn_adapter import ProviderContextUnavailable
from probe_live_access import fetch_json, BASE


class PregameNotReady(ProviderContextUnavailable):
    pass


def current_event(canonical, espn_event_id, fetcher=fetch_json):
    if not str(espn_event_id).isdigit():
        raise ProviderContextUnavailable('Invalid mapped event ID')
    day=canonical['gameDate']
    board,_=fetcher(BASE+'scoreboard?dates='+day.replace('-',''))
    matches=[event for event in board['events'] if str(event['id'])==str(espn_event_id)]
    if len(matches)!=1:
        raise ProviderContextUnavailable('Mapped event missing or duplicated')
    event=matches[0]
    competition,=event['competitions']
    timestamp=datetime.fromisoformat(competition['date'].replace('Z','+00:00'))
    if (timestamp.tzinfo is None or timestamp.astimezone(ZoneInfo('America/New_York')).date().isoformat()!=day or
            event['season']['year']!=int(canonical['season'][:4])+1 or event['season']['type']!=2):
        raise ProviderContextUnavailable('Wrong mapped event context')
    return event


def fetch_pair(canonical, espn_event_id, fetcher=fetch_json):
    event=current_event(canonical,espn_event_id,fetcher)
    return summary_pair(event,espn_event_id,fetcher)


def summary_pair(event,espn_event_id,fetcher=fetch_json):
    if str(event['id'])!=str(espn_event_id) or not str(espn_event_id).isdigit():
        raise ProviderContextUnavailable('Invalid mapped summary event')
    if event['competitions'][0]['status']['type']['state']=='pre':
        raise PregameNotReady('Game has not started; no in-game estimate is available')
    summary,_=fetcher(BASE+'summary?event='+str(espn_event_id))
    return {'event':event,'summary':summary}
