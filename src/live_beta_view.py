"""Private limited-beta renderer, activated only by reviewed cloud config."""

from datetime import datetime
import json
from pathlib import Path
import runpy
import time
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
from live_diagnostics import diagnostics
from live_rollout import MAX_LIVE_GAMES
from live_game_date import eligible_game_date, overnight_game
from live_operations import operations_status


@st.cache_resource
def resources(capacity=MAX_LIVE_GAMES):
    return LiveSnapshotCache(max_entries=capacity),FeedProgress(max_entries=capacity)


@st.cache_resource
def cpu_artifacts():
    return load_cpu_artifacts()


@st.cache_data(ttl=15,max_entries=MAX_LIVE_GAMES,show_spinner=False)
def scoreboard_event(canonical,event_id):
    return current_event(canonical,event_id)


def render_readiness(root):
    health=operations_status(root)
    with st.expander('Data readiness'):
        st.caption('Release: owner-beta-daily-v1 · private access · automatic preparation runs on your Mac, not in this page.')
        if health['preparation']=='unavailable':
            st.info('Daily preparation is not available yet. A reviewed manual beta window may still be active.')
        else:
            st.write(f"{health['gameDate']} · {health['preparedGames']} prepared matchups · {health['preparation']}")
            st.caption(f"Prepared at {health['preparedAt']} · expires {health['expiresAt']}")
            if health['rosterTeamsUnavailable'] or health['pendingIdentities']:
                st.warning('Some roster identities still need verification. Affected estimates may be unavailable.')
            if health['deferredGames']:
                st.caption(f"{health['deferredGames']} additional games are outside this four-game beta limit.")


def render_live_beta(root,allowed_games,rollout_guard=None):
    st.title('Game Center')
    st.caption('Private Live beta · verified matchups · frozen V7')
    root=Path(root)
    now=datetime.now(ZoneInfo('America/New_York'))
    path=root/'results/live_context'/f'{CURRENT_SEASON}_day_context_v1.json'
    render=runpy.run_path(str(root/'src/live_preview_view.py'))['render_live_analysis']
    if not allowed_games or len(allowed_games)>MAX_LIVE_GAMES or len(set(allowed_games))!=len(allowed_games):
        render(None);return
    try:
        day=json.loads(path.read_text())
        if not eligible_game_date(day['gameDate'], now):
            raise ValueError('Wrong day')
        games={g['gameId']:g for g in day['games'] if g['gameId'] in allowed_games}
        if not games:
            raise ValueError('No verified games')
    except (OSError,ValueError,KeyError,TypeError):
        render(None);return
    registry={team['id']:team['abbreviation'] for team in teams.get_teams()}
    game_control,refresh_control=st.columns([3,2])
    selected=game_control.selectbox('Game',list(games),format_func=lambda gid:
        f"{registry[games[gid]['awayTeamId']]} @ {registry[games[gid]['homeTeamId']]}")
    game=games[selected]
    canonical={k:game[k] for k in ('gameId','gameDate','season','homeTeamId','awayTeamId')}
    auto=refresh_control.toggle('Refresh every 15 seconds',value=False)
    st.caption('Manual refresh by default. A paused browser is not a background monitor.')

    @st.fragment(run_every='15s' if auto else None)
    def panel():
        started=time.perf_counter()
        st.button('Refresh game',key='live_beta_refresh')
        if rollout_guard is not None and selected not in rollout_guard():
            diagnostics.record(selected,'paused',time.perf_counter()-started)
            st.info('Live is paused or this rollout has expired. Return to Season Intelligence in the sidebar.')
            return
        try:
            mapped=read_day_context(path,canonical)  # Gate before all HTTP/model work.
            event=scoreboard_event(canonical,mapped['espnEventId'])
            if event['competitions'][0]['status']['type']['state']=='pre':
                if overnight_game(canonical['gameDate'], datetime.now(ZoneInfo('America/New_York'))):
                    raise ValueError('Previous-day game has not started')
                diagnostics.record(selected,'scheduled',time.perf_counter()-started)
                st.subheader(f"{registry[canonical['awayTeamId']]} at {registry[canonical['homeTeamId']]}")
                st.info('Scheduled · this game has not started. No in-game estimate is shown.')
                st.caption('Verified pregame regular-season records are ready; check back after tip-off.')
                return
            cache,tracker=resources(MAX_LIVE_GAMES)
            result=analyze_live_snapshot(cache,canonical,path,
                lambda:summary_pair(event,mapped['espnEventId']),cpu_artifacts(),tracker)
            render(result,registry[canonical['homeTeamId']],registry[canonical['awayTeamId']])
            diagnostics.record(selected,result.display_state,time.perf_counter()-started,age=result.snapshot.age_seconds,
                error_type=result.snapshot.refresh_error_type)
        except (RuntimeError,ValueError,KeyError,TypeError,OSError,IndexError) as error:
            diagnostics.record(selected,'unavailable',time.perf_counter()-started,error_type=type(error).__name__)
            # No provider exception details, guessed probabilities or neutral records.
            render(None)
            st.caption('Waiting for a coherent feed and verified context. Try refreshing shortly.')
    panel()
    render_readiness(root)
