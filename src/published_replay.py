"""Read-only replay pilot. Never fetch feeds, unpickle data, or run inference."""

import json
from pathlib import Path

import pandas as pd

PILOT_PATH = Path(__file__).resolve().parents[1] / "results/replay_pilot/0022500001.json"


def load_replay(path=PILOT_PATH):
    data = json.loads(Path(path).read_text())
    if data.get("schemaVersion") != 1 or data.get("model") != "Frozen V7":
        raise ValueError("Unsupported replay artifact")
    timeline = pd.DataFrame(data["timeline"])
    if timeline.empty or not timeline.elapsedGameTime.is_monotonic_increasing:
        raise ValueError("Replay timeline is missing or out of order")
    if not timeline.winProbability.between(0, 1).all():
        raise ValueError("Invalid replay probabilities")
    for side in ("home", "away"):
        team = data[side]
        if int(timeline.iloc[-1]["scoreHome" if side == "home" else "scoreAway"]) != team["score"]:
            raise ValueError("Final timeline score mismatch")
        points = sum(row["points"] for row in data["boxScore"] if row["teamTricode"] == team["tricode"])
        if points != team["score"]:
            raise ValueError("Box score does not reconcile")
    return data, timeline


def render_replay():
    import plotly.graph_objects as go
    import streamlit as st

    st.subheader("Historical Replay · Pilot")
    st.caption("Precomputed full-game analysis · Frozen V7 · no live feed or inference")
    try:
        data, timeline = load_replay()
    except (OSError, ValueError, KeyError, TypeError) as error:
        st.error("This replay is temporarily unavailable. Season Intelligence is still available in the sidebar.")
        return
    home, away = data["home"], data["away"]
    st.markdown(f"### {away['tricode']} {away['score']} · {home['tricode']} {home['score']}")
    st.caption(f"{data['date']} · {data['season']} regular season · Final / 2OT")
    st.info("Final scores, turning points, player impact, and box scores include the entire game. The timeline slider is for inspection, not spoiler-free playback.")
    index = st.slider("Inspect timeline event", 0, len(timeline) - 1, len(timeline) - 1)
    row = timeline.iloc[index]
    st.caption(f"Period {int(row['period'])} · {row['clock']} · {away['tricode']} {int(row['scoreAway'])} – {home['tricode']} {int(row['scoreHome'])}")
    st.write(str(row["description"]))
    chart = go.Figure()
    for name, values, color in [(home["tricode"], timeline.winProbability * 100, "#58A6FF"),
                                 (away["tricode"], (1 - timeline.winProbability) * 100, "#F5B841")]:
        chart.add_trace(go.Scatter(x=timeline.elapsedGameTime / 60, y=values, name=name,
                                  line=dict(color=color, width=2), hovertemplate="%{x:.1f} min · %{y:.1f}%<extra>%{fullData.name}</extra>"))
    chart.add_vline(x=float(row.elapsedGameTime) / 60, line_dash="dot")
    chart.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10),
                        xaxis_title="Elapsed minutes", yaxis_title="Win probability (%)",
                        yaxis_range=[0, 100], legend=dict(orientation="h"))
    st.plotly_chart(chart, width="stretch")
    turning, impact, box = st.tabs(["Turning Points", "Player Impact", "Box Score"])
    with turning:
        st.caption("Largest precomputed swings for each side · full game")
        st.dataframe(pd.DataFrame(data["turningPoints"]), hide_index=True, width="stretch")
    with impact:
        st.caption("Frozen attributed full-game WPA—not wins added or a causal player estimate.")
        st.dataframe(pd.DataFrame(data["playerImpact"]), hide_index=True, width="stretch")
    with box:
        st.caption("Cached final box score · player points reconcile to both final team scores")
        st.dataframe(pd.DataFrame(data["boxScore"]), hide_index=True, width="stretch")
