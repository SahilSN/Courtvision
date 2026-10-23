"""Readable replay chart with redundant team identification and mobile-safe legend."""

import plotly.graph_objects as go


def build_replay_chart(data, timeline, index):
    home, away = data["home"], data["away"]
    chart = go.Figure()
    for name, values, color, dash in [
        (home["tricode"], timeline.winProbability * 100, "#58A6FF", "solid"),
        (away["tricode"], (1 - timeline.winProbability) * 100, "#F5B841", "solid"),
    ]:
        chart.add_trace(go.Scatter(x=timeline.elapsedGameTime / 60, y=values, name=name,
            line=dict(color=color, width=3, dash=dash),
            hovertemplate="%{x:.1f} min · %{y:.1f}%<extra>%{fullData.name}</extra>"))
    chart.add_vline(x=float(timeline.iloc[index].elapsedGameTime) / 60, line_dash="dot")
    chart.update_layout(height=370, margin=dict(l=12, r=12, t=55, b=55),
        xaxis_title="Elapsed minutes", yaxis_title="Win probability (%)", yaxis_range=[0, 100],
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0))
    return chart
