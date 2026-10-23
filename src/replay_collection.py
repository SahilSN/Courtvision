"""Curated offline replays; selection never expands into unrestricted analysis."""

import math
import re

import pandas as pd

from published_replay import PILOT_PATH, load_replay

GAME_IDS = ("0022500001", "0022500009", "0022500365", "0022500581")


def clock_label(value):
    match = re.fullmatch(r"PT(\d+)M(\d+(?:\.\d+)?)S", str(value))
    return f"{int(match[1])}:{int(float(match[2])):02d}" if match else str(value)


def final_label(period):
    period = int(period)
    return "Final" if period <= 4 else f"Final / {period - 4}OT"


def load_collection(directory=PILOT_PATH.parent):
    collection = {}
    for game_id in GAME_IDS:
        data, timeline = load_replay(directory / f"{game_id}.json")
        if data["gameId"] != game_id or data["season"] != "2025-26":
            raise ValueError("Replay identity does not match curated collection")
        for field in ("elapsedGameTime", "winProbability", "scoreHome", "scoreAway", "period"):
            if not all(math.isfinite(float(v)) for v in timeline[field]):
                raise ValueError("Non-finite replay data")
        if timeline.elapsedGameTime.min() < 0 or timeline.period.min() < 1:
            raise ValueError("Invalid replay clock")
        for field in ("turningPoints", "boxScore", "playerImpact"):
            if not data[field]:
                raise ValueError("Missing full-game replay panel")
        collection[game_id] = (data, timeline)
    return collection


def render_replay_collection():
    import plotly.graph_objects as go
    import streamlit as st

    st.subheader("Historical Replay · Collection")
    st.caption("Four curated games · precomputed full-game analysis · Frozen V7 · no live feed or inference")
    try:
        collection = load_collection()
    except (OSError, ValueError, KeyError, TypeError):
        st.error("The replay collection is temporarily unavailable. Season Intelligence remains available in the sidebar.")
        return
    selected = st.selectbox("Choose a replay", list(collection),
        format_func=lambda gid: f"{collection[gid][0]['away']['tricode']} @ {collection[gid][0]['home']['tricode']} · {collection[gid][0]['date']}",
        key="published_replay_game")
    data, timeline = collection[selected]
    home, away = data["home"], data["away"]
    st.markdown(f"### {away['tricode']} {away['score']} · {home['tricode']} {home['score']}")
    st.caption(f"{data['date']} · {data['season']} regular season · {final_label(timeline.period.max())}")
    st.info("Full-game results and summaries contain spoilers. The timeline slider inspects a moment; it does not hide later plays, the final result, player impact, or box scores.")
    index = st.slider("Inspect timeline event", 0, len(timeline) - 1, len(timeline) - 1,
                      key=f"replay_event_{selected}")
    row = timeline.iloc[index]
    period = int(row.period)
    period_text = f"Q{period}" if period <= 4 else f"OT{period - 4}"
    st.caption(f"{period_text} · {clock_label(row.clock)} · {away['tricode']} {int(row.scoreAway)} – {home['tricode']} {int(row.scoreHome)}")
    st.write(str(row.description))
    chart = go.Figure()
    for name, values, color in [(home["tricode"], timeline.winProbability * 100, "#58A6FF"),
                                (away["tricode"], (1 - timeline.winProbability) * 100, "#F5B841")]:
        chart.add_trace(go.Scatter(x=timeline.elapsedGameTime / 60, y=values, name=name,
            line=dict(color=color, width=2), hovertemplate="%{x:.1f} min · %{y:.1f}%<extra>%{fullData.name}</extra>"))
    chart.add_vline(x=float(row.elapsedGameTime) / 60, line_dash="dot")
    chart.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), xaxis_title="Elapsed minutes",
                        yaxis_title="Win probability (%)", yaxis_range=[0, 100], legend=dict(orientation="h"))
    st.plotly_chart(chart, width="stretch")
    turning, impact, box = st.tabs(["Turning Points", "Player Impact", "Box Score"])
    with turning:
        st.caption("Largest cached swings for each side · full game. Changes below are from the home team's perspective.")
        swings = pd.DataFrame(data["turningPoints"]).copy()
        swings["Clock"] = swings.Clock.map(clock_label)
        st.dataframe(swings, hide_index=True, width="stretch")
    with impact:
        st.caption("Frozen attributed full-game WPA in percentage points—not wins added or a causal estimate.")
        players = pd.DataFrame(data["playerImpact"]).sort_values("netWPAPoints", ascending=False)
        st.dataframe(players.rename(columns={"playerName": "Player", "teamTricode": "Team",
            "events": "Attributed Events", "netWPAPoints": "Net WPA (pp)"}), hide_index=True, width="stretch")
    with box:
        st.caption("Cached final box score · both teams' player points match the final score")
        team = st.selectbox("Box score team", ["All teams", away["tricode"], home["tricode"]],
                            key=f"replay_box_team_{selected}")
        players = pd.DataFrame(data["boxScore"])
        if team != "All teams":
            players = players.loc[players.teamTricode.eq(team)]
        st.dataframe(players.rename(columns={"fullName": "Player", "teamTricode": "Team", "minutesDisplay": "MIN",
            "points": "PTS", "reboundsTotal": "REB", "assists": "AST", "steals": "STL", "blocks": "BLK", "turnovers": "TO"}),
            hide_index=True, width="stretch")
