"""Private-beta operations panel; offline reads only, no worker control buttons."""

import streamlit as st

from deployment_health import intelligence_status
from live_diagnostics import diagnostics
from live_operations import operations_status
from ui_shell import time_label


def render_health(root):
    with st.sidebar.expander('Update health'):
        st.caption('Published evidence as of page load · Pacific time. This page does not run updates.')
        for name, item in intelligence_status(root)['pipelines'].items():
            st.markdown(f'**{name.title()} · {item["state"]}**')
            if 'lastCheckAt' in item:
                st.caption(f'Last check: {time_label(item["lastCheckAt"])}')
                total = item['completedGames'] if item['completedGames'] is not None else 'unknown'
                st.caption(f'{item["processedGames"]}/{total} completed games · games through {item["gamesThrough"] or "none yet"}')
            st.caption(item['action'])
        live = operations_status(root)
        st.markdown(f'**Live preparation · {live["preparation"]}**')
        if 'preparedAt' in live:
            st.caption(f'{live["gameDate"]} · prepared {time_label(live["preparedAt"])} · expires {time_label(live["expiresAt"])}')
            st.caption(f'{live["preparedGames"]} prepared · {live["deferredGames"]} deferred · '
                       f'{live["rosterTeamsUnavailable"]} roster teams unavailable · {live["pendingIdentities"]} identity reviews')
        if live['preparation'] != 'prepared':
            st.caption('Check nightly preparation and the dated identity review queue. Never guess player IDs or bypass validation.')
        st.caption(f'{len(live["activeGameIds"])} policy-eligible games; this is not feed or runtime certification.')
        recent = diagnostics.recent()
        st.markdown('**Recent feed observations**')
        st.caption('This process only, last two minutes, as of page load—not continuous monitoring. Reload the page to update this panel.')
        if not recent:
            st.caption('No recent observations. Open an eligible game to observe its feed; absence is not a provider outage.')
        for item in recent:
            st.caption(f'{item["gameId"]} · {item["state"]} · observed {item["observedSecondsAgo"]:.0f}s ago')
        st.caption('If feeds fail, retain only unexpired verified data. Use Refresh game; do not force estimates.')
        st.caption('Mac nightly job: 1 a.m. local time. This hosted snapshot cannot prove the Mac is awake or the next job will succeed.')
        from live_artifacts import read_json
        try:
            replay = read_json(root / 'results/replay_catalog/expansion_status_v1.json')
        except (OSError, ValueError, TypeError):
            st.caption('Replay expansion: no published worker snapshot yet.')
        else:
            st.markdown('**Historical replay expansion**')
            st.caption(f'{replay["publishedReplayCount"]} published replays · '
                       f'{replay["blockedGames"]} blocked attempted games · '
                       f'worker checked {time_label(replay["checkedAt"])}')
            st.caption('2024–25 paused for opening-state repair. Local preparation resumes while your Mac is awake; '
                       'validated batches publish nightly after 1:30 a.m. Pacific. This is a published snapshot, not a live worker monitor.')
