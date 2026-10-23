"""Responsive offline replay screen; all jumps share the timeline's event state."""

import pandas as pd

from replay_collection import clock_label, final_label, load_collection
from replay_exploration import game_overview, replay_bookmarks, set_replay_event


def render_replay_view():
    import plotly.graph_objects as go
    import streamlit as st

    st.subheader("Historical Replay · Collection")
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
    index = st.slider("Inspect timeline event", 0, len(timeline) - 1, len(timeline) - 1, key=f"replay_event_{selected}")
    row = timeline.iloc[index]
    period = int(row.period)
    label = f"Q{period}" if period <= 4 else f"OT{period - 4}"
    st.caption(f"{label} · {clock_label(row.clock)} · {away['tricode']} {int(row.scoreAway)} – {home['tricode']} {int(row.scoreHome)}")
    st.write(str(row.description))
    chart = go.Figure()
    for name, values, color in [(home["tricode"], timeline.winProbability * 100, "#58A6FF"),
                                (away["tricode"], (1 - timeline.winProbability) * 100, "#F5B841")]:
        chart.add_trace(go.Scatter(x=timeline.elapsedGameTime / 60, y=values, name=name, line=dict(color=color, width=2),
            hovertemplate="%{x:.1f} min · %{y:.1f}%<extra>%{fullData.name}</extra>"))
    chart.add_vline(x=float(row.elapsedGameTime) / 60, line_dash="dot")
    chart.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Elapsed minutes",
                        yaxis_title="Win probability (%)", yaxis_range=[0, 100], legend=dict(orientation="h"))
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
                    st.button("Inspect this play", key=f"replay_card_{selected}_{number}",
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
