"""Display-only full-game summaries and exact-event navigation for offline replays."""

from replay_collection import GAME_IDS, clock_label, load_collection, render_replay_collection


def game_overview(data, timeline):
    home, away = data["home"], data["away"]
    margin = home["score"] - away["score"]
    winner = home["tricode"] if margin > 0 else away["tricode"]
    overtime = max(0, int(timeline.period.max()) - 4)
    ending = "in regulation" if not overtime else f"after {overtime} overtime period{'s' if overtime != 1 else ''}"
    differences = timeline.scoreHome - timeline.scoreAway
    return (f"{winner} won by {abs(margin)} point{'s' if abs(margin) != 1 else ''} {ending}. "
            f"Largest recorded leads: {home['tricode']} {max(0, int(differences.max()))}; "
            f"{away['tricode']} {max(0, int(-differences.min()))}. "
            "These are descriptive facts from the published full-game timeline, not explanations of why a team won.")


def replay_bookmarks(data, timeline):
    periods = []
    for period in sorted(timeline.period.unique()):
        indices = timeline.index[timeline.period.eq(period)]
        label = f"Q{int(period)}" if period <= 4 else f"OT{int(period) - 4}"
        periods.append((f"{label} · first recorded event", int(indices[0])))
    swings = []
    for number, swing in enumerate(data["turningPoints"], 1):
        matches = timeline.index[timeline.period.eq(swing["Period"]) &
                                 timeline.clock.eq(swing["Clock"]) & timeline.description.eq(swing["Play"])]
        # Do not invent a nearest-event match or silently choose an ambiguous play.
        if len(matches) == 1:
            swings.append((f"{number}. {swing['Side']} · P{swing['Period']} {clock_label(swing['Clock'])} · {swing['Play']}", int(matches[0])))
    return periods, swings


def set_replay_event(game_id, index):
    import streamlit as st
    st.session_state[f"replay_event_{game_id}"] = index


def render_explorable_replays():
    import streamlit as st

    render_replay_collection()
    selected = st.session_state.get("published_replay_game", GAME_IDS[0])
    try:
        data, timeline = load_collection()[selected]
    except (OSError, ValueError, KeyError, TypeError):
        return  # The main renderer already reports unavailable artifacts.
    st.divider()
    st.subheader("Game overview & quick jumps")
    st.write(game_overview(data, timeline))
    st.caption("Full-game spoilers · jumps update the timeline marker above; all summary panels remain full-game.")
    periods, swings = replay_bookmarks(data, timeline)
    choice = st.selectbox("Jump to a period", range(len(periods)),
                          format_func=lambda index: periods[index][0], key=f"replay_period_{selected}")
    st.button("Inspect period on timeline", key=f"replay_jump_period_{selected}",
              on_click=set_replay_event, args=(selected, periods[choice][1]))
    if swings:
        choice = st.selectbox("Jump to a turning point", range(len(swings)),
                              format_func=lambda index: swings[index][0], key=f"replay_swing_{selected}")
        st.button("Inspect turning point on timeline", key=f"replay_jump_swing_{selected}",
                  on_click=set_replay_event, args=(selected, swings[choice][1]))
    if len(swings) != len(data["turningPoints"]):
        st.caption("Only turning points with a unique exact timeline match are offered as jumps.")
