"""Private limited-beta renderer, activated only by reviewed cloud config."""

from datetime import datetime
import json
from pathlib import Path
import runpy
from zoneinfo import ZoneInfo

import streamlit as st
from nba_api.stats.static import teams

from cloud_live_analysis import analyze_live_snapshot
from daily_live_context import read_day_context
from feed_progress import FeedProgress
from live_refresh import current_event, summary_pair
from live_snapshot_cache import LiveSnapshotCache
from offline_live_sample import load_cpu_artifacts
from season_config import CURRENT_SEASON


@st.cache_resource
def resources():
    return LiveSnapshotCache(max_entries=2),FeedProgress(max_entries=2)


@st.cache_resource
def cpu_artifacts():
    return load_cpu_artifacts()


@st.cache_data(ttl=15,max_entries=2,show_spinner=False)
def scoreboard_event(canonical,event_id):
    return current_event(canonical,event_id)


def render_live_beta(root,allowed_games):
    st.title('Game Center · Live check')
    st.caption('Two-game testing scope · frozen V7 · refreshes are paused unless enabled below')
    root=Path(root)
    today=datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    path=root/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json'
    render=runpy.run_path(str(root/'src/live_preview_view.py'))['render_live_analysis']
    try:
        day=json.loads(path.read_text())
        if day['gameDate']!=today:
            raise ValueError('Wrong day')
        games={g['gameId']:g for g in day['games'] if g['gameId'] in allowed_games}
        if not games:
            raise ValueError('No verified games')
    except (OSError,ValueError,KeyError,TypeError):
        render(None);return
    registry={team['id']:team['abbreviation'] for team in teams.get_teams()}
    selected=st.selectbox('Game',list(games),format_func=lambda gid:
        f"{registry[games[gid]['awayTeamId']]} @ {registry[games[gid]['homeTeamId']]}")
    game=games[selected]
    canonical={k:game[k] for k in ('gameId','gameDate','season','homeTeamId','awayTeamId')}
    auto=st.toggle('Refresh every 15 seconds',value=False)
    st.caption('Manual refresh by default. A paused browser is not a background monitor.')

    @st.fragment(run_every='15s' if auto else None)
    def panel():
        st.button('Refresh game',key='live_beta_refresh')
        try:
            mapped=read_day_context(path,canonical)  # Gate before all HTTP/model work.
            event=scoreboard_event(canonical,mapped['espnEventId'])
            if event['competitions'][0]['status']['type']['state']=='pre':
                st.info('Scheduled · this game has not started. No in-game estimate is shown.')
                st.caption('Verified pregame regular-season records are ready; check back after tip-off.')
                return
            cache,tracker=resources()
            result=analyze_live_snapshot(cache,canonical,path,
                lambda:summary_pair(event,mapped['espnEventId']),cpu_artifacts(),tracker)
            render(result,registry[canonical['homeTeamId']],registry[canonical['awayTeamId']])
        except (RuntimeError,ValueError,KeyError,TypeError,OSError,IndexError):
            # No provider exception details, guessed probabilities or neutral records.
            render(None)
            st.caption('Waiting for a coherent feed and verified context. Try refreshing shortly.')
    panel()
