"""Responsive offline replay screen; all jumps share the timeline's event state."""

import pandas as pd

from replay_collection import clock_label, final_label, load_collection
from replay_exploration import game_overview, replay_bookmarks, set_replay_event
from replay_chart import build_replay_chart


def render_replay_view():
    import streamlit as st

    from ui_shell import page_heading
    page_heading('Replay Collection','Revisit four curated games with frozen win probabilities, turning points and player impact.',
                 'Historical replay · Limited collection')
    st.caption("Four curated games · precomputed full-game analysis · Frozen V7 · no live feed or inference")
    try:
        collection = load_collection()
    except (OSError, ValueError, KeyError, TypeError):
        st.error("The replay collection is temporarily unavailable. Season Intelligence remains available in the sidebar.")
        return
    selected = st.selectbox("Choose a replay", list(collection), key="published_replay_game",
        format_func=lambda gid: f"{collection[gid][0]['away']['tricode']} @ {collection[gid][0]['home']['tricode']} · {collection[gid][0]['date']}")
    data, timeline = collection[selected]
    home, away = data["home"], data["away"]
    st.markdown(f"### {away['tricode']} {away['score']} · {home['tricode']} {home['score']}")
    st.caption(f"{data['date']} · {data['season']} regular season · {final_label(timeline.period.max())}")
    st.info("Full-game spoilers: scores, summaries, chart, player impact and box scores include the entire game. Jumps only move the timeline marker—not spoiler-free playback.")
    with st.expander("Game overview"):
        st.write(game_overview(data, timeline))
    periods, swings = replay_bookmarks(data, timeline)
    with st.expander("Quick jumps · periods & turning points", expanded=True):
        left, right = st.columns(2)
        with left:
            period = st.selectbox("Jump to a period", range(len(periods)), key=f"replay_period_{selected}",
                                  format_func=lambda i: periods[i][0])
            st.button("Inspect period on timeline", key=f"replay_jump_period_{selected}",
                      on_click=set_replay_event, args=(selected, periods[period][1]))
        with right:
            if swings:
                swing = st.selectbox("Jump to a turning point", range(len(swings)), key=f"replay_swing_{selected}",
                                     format_func=lambda i: swings[i][0])
                st.button("Inspect turning point on timeline", key=f"replay_jump_swing_{selected}",
                          on_click=set_replay_event, args=(selected, swings[swing][1]))
        if len(swings) != len(data["turningPoints"]):
            st.caption("Only uniquely matched turning points are offered as jumps.")
    index = st.slider("Inspect timeline event", 0, len(timeline) - 1, len(timeline) - 1, key=f"replay_event_{selected}",
                      help="Keyboard: arrow keys move between events; Home and End select the first and last events. Full-game spoilers remain visible.")
    row = timeline.iloc[index]
    period = int(row.period)
    label = f"Q{period}" if period <= 4 else f"OT{period - 4}"
    st.caption(f"{label} · {clock_label(row.clock)} · {away['tricode']} {int(row.scoreAway)} – {home['tricode']} {int(row.scoreHome)}")
    st.write(str(row.description))
    st.write(f"Selected-event win probability: {home['tricode']} {float(row.winProbability):.1%}; "
             f"{away['tricode']} {1 - float(row.winProbability):.1%}.")
    st.caption(f"Chart key: {home['tricode']} blue; {away['tricode']} gold. Both lines are solid. "
               "The text above gives the selected score and probabilities without relying on chart color or hover.")
    chart = build_replay_chart(data, timeline, index)
    # Also apply the preference here for hosts retaining an older chart helper.
    chart.update_traces(line_dash="solid")
    st.plotly_chart(chart, width="stretch")
    turning, impact, box = st.tabs(["Turning Points", "Player Impact", "Box Score"])
    with turning:
        st.caption("Cached full-game swings. Signed changes are from the home team's perspective.")
        for number, point in enumerate(data["turningPoints"], 1):
            with st.container(border=True):
                st.markdown(f"**{point['Side']} · P{point['Period']} · {clock_label(point['Clock'])}**")
                st.write(point["Play"])
                st.caption(f"{home['tricode']} win probability change: {point['Home probability change (pp)']:+.2f} percentage points")
                match = next((index for text, index in swings if text.startswith(f"{number}. ")), None)
                if match is not None:
                    st.button(f"Inspect play {number} · P{point['Period']} {clock_label(point['Clock'])}", key=f"replay_card_{selected}_{number}",
                              on_click=set_replay_event, args=(selected, match))
    with impact:
        st.caption("Frozen attributed full-game WPA in percentage points—not wins added or a causal estimate.")
        players = pd.DataFrame(data["playerImpact"]).sort_values("netWPAPoints", ascending=False)
        st.dataframe(players.rename(columns={"playerName": "Player", "teamTricode": "Team", "events": "Attributed Events",
                     "netWPAPoints": "Net WPA (pp)"}), hide_index=True, width="stretch",
                     column_config={"Net WPA (pp)": st.column_config.NumberColumn(format="%.2f")})
    with box:
        st.caption("Cached final box score · both teams' player points match the final score")
        team = st.selectbox("Box score team", ["All teams", away["tricode"], home["tricode"]], key=f"replay_box_team_{selected}")
        players = pd.DataFrame(data["boxScore"])
        if team != "All teams":
            players = players.loc[players.teamTricode.eq(team)]
        st.dataframe(players.rename(columns={"fullName": "Player", "teamTricode": "Team", "minutesDisplay": "MIN",
                     "points": "PTS", "reboundsTotal": "REB", "assists": "AST", "steals": "STL", "blocks": "BLK", "turnovers": "TO"}),
                     hide_index=True, width="stretch")
