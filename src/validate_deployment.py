"""Offline deployment smoke test; run from a clean checkout after installation.

Uses bundled artifacts only. No NBA calls, workers, or publication are allowed.
This checks app execution, not visual layout, browser assets, or load capacity.
"""

import argparse
import os
from pathlib import Path
from unittest.mock import patch

# Import before intercepting subprocesses: Matplotlib can query system fonts.
import matplotlib.pyplot  # noqa: F401
import joblib
import numpy as np
import pandas as pd
import torch
from streamlit.testing.v1 import AppTest

from feature_engineering import MODEL_FEATURES
from model import WinProbabilityMLP
from player_career import build_player_career, load_published_player_data
from season_config import CURRENT_SEASON

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def check_render(app):
    require(not app.exception, f"Uncaught UI exception: {app.exception}")
    require(not app.error, f"UI error: {app.error}")


def validate_model():
    """Exercise the unchanged frozen artifacts explicitly on deployment CPU."""
    scaler = joblib.load(ROOT / "models/win_probability_scaler_v7.pkl")
    model = WinProbabilityMLP(input_size=len(MODEL_FEATURES))
    model.load_state_dict(torch.load(
        ROOT / "models/win_probability_mlp_v7.pt", map_location="cpu",
        weights_only=True,
    ))
    model.eval()
    features = pd.DataFrame(np.zeros((1, len(MODEL_FEATURES))), columns=MODEL_FEATURES)
    with torch.no_grad():
        probability = torch.sigmoid(model(torch.tensor(
            scaler.transform(features), dtype=torch.float32,
        )))
    require(bool(torch.isfinite(probability).all()), "Non-finite frozen-model output")
    require(probability.shape == (1, 1), "Unexpected frozen-model output shape")
    print("PASS: frozen V7/scaler load and CPU inference")


def validate_published_app(entrypoint="dashboard/app.py"):
    entrypoint_path = (ROOT / entrypoint).resolve()
    is_cloud_entrypoint = entrypoint_path == ROOT / "cloud" / "app.py"
    summaries, games, coverage = load_published_player_data()
    require(not summaries.empty and not games.empty, "Missing published player data")
    require(CURRENT_SEASON in set(coverage.season), "Current player season missing")
    for person_id in games.personId.unique():
        build_player_career(games, person_id)

    with patch.dict(os.environ, {
             # The cloud wrapper must override even an incorrectly configured full profile.
             "COURTVISION_DEPLOYMENT_PROFILE": "full" if is_cloud_entrypoint else "published",
             "COURTVISION_CLOUD_READY": "1",
         }), \
         patch("requests.sessions.Session.request", side_effect=AssertionError(
             "Published deployment attempted a network request")) as network, \
         patch("subprocess.Popen", side_effect=AssertionError(
             "Published deployment attempted a subprocess")) as workers:
        app = AppTest.from_file(str(entrypoint_path), default_timeout=90)
        # Old browser sessions must not retain a disabled mode after deployment.
        app.session_state["courtvision_mode"] = "Live"
        app.run()
        check_render(app)
        mode = app.sidebar.radio(key="courtvision_mode")
        require(mode.options == ["Season Intelligence"], "Published mode leaks game navigation")
        require(mode.value == "Season Intelligence", "Disabled mode retained in session")
        season_picker = app.sidebar.selectbox(key="courtvision_season_intelligence_season")
        require(season_picker.value == CURRENT_SEASON, "Current season is not the default")
        seasons = list(season_picker.options)

        for view in ("Teams", "Players"):
            app.sidebar.radio(key="courtvision_season_intelligence_view").set_value(view).run()
            check_render(app)
            for season in seasons:
                app.sidebar.selectbox(key="courtvision_season_intelligence_season").select(season).run()
                check_render(app)
            print(f"PASS: {view}, {len(seasons)} published seasons")

        app.sidebar.radio(key="courtvision_season_intelligence_view").set_value("Player Career").run()
        check_render(app)
        print("PASS: career view and every published player's career aggregation")

        person_id = app.selectbox(key="courtvision_player_career_person").value
        target = app.selectbox(key=f"career_explore_season_{person_id}").value
        first_key = f"career_compare_first_{person_id}"
        if any(box.key == first_key for box in app.selectbox):
            picker = app.selectbox(key=first_key)
            picker.select(picker.options[-1]).run()
            check_render(app)
            require(app.selectbox(key=f"career_compare_second_{person_id}").value !=
                    app.selectbox(key=first_key).value, "Comparison permits duplicate seasons")
        app.button(key=f"career_open_season_{person_id}").click().run()
        check_render(app)
        require(app.sidebar.radio(key="courtvision_season_intelligence_view").value == "Players",
                "Career-to-season navigation failed")
        require(app.selectbox(key=f"courtvision_player_intelligence_player_{target}").value == person_id,
                "Season navigation lost selected player")
        require(app.session_state[f"courtvision_player_tab_{target}"] == "Player Explorer",
                "Season navigation did not open explorer")
        app.button(key=f"career_from_{target}").click().run()
        check_render(app)
        require(app.selectbox(key="courtvision_player_career_person").value == person_id,
                "Season-to-career navigation lost selected player")
        print("PASS: distinct-season comparison and player-preserving career/season round trip")

        app.sidebar.radio(key="courtvision_season_intelligence_view").set_value("Replay Pilot").run()
        check_render(app)
        from replay_collection import GAME_IDS
        for game_id in GAME_IDS:
            app.selectbox(key="published_replay_game").set_value(game_id).run()
            check_render(app)
            app.slider[0].set_value(0).run()
            check_render(app)
            app.slider[0].set_value(app.slider[0].max).run()
            check_render(app)
            from replay_exploration import replay_bookmarks
            from replay_collection import load_collection
            data, timeline = load_collection()[game_id]
            periods, swings = replay_bookmarks(data, timeline)
            app.button(key=f"replay_jump_period_{game_id}").click().run()
            check_render(app)
            require(app.slider[0].value == periods[0][1], "Period jump missed its exact event")
            app.button(key=f"replay_jump_swing_{game_id}").click().run()
            check_render(app)
            require(app.slider[0].value == swings[0][1], "Turning-point jump missed its exact event")
            card = next(button for button in app.button if str(button.key).startswith(f"replay_card_{game_id}_"))
            card.click().run()
            check_render(app)
            require(app.slider[0].value == swings[0][1], "Turning-point card missed its exact event")
            require(any("Selected-event win probability" in text.value for text in app.markdown),
                    "Replay must expose selected probabilities outside the chart")
            labels = [button.label for button in app.button if str(button.key).startswith(f"replay_card_{game_id}_")]
            require(len(labels) == len(set(labels)), "Turning-point buttons need distinct accessible labels")
        require(any("full-game" in caption.value.lower() for caption in app.caption),
                "Replay must disclose full-game precomputation")
        app.sidebar.radio(key="courtvision_season_intelligence_view").set_value("Player Career").run()
        check_render(app)
        print("PASS: all four offline replays, first/final event inspection, and return to career")

        app.sidebar.radio(key="courtvision_season_intelligence_view").set_value("Replay Pilot").run()
        with patch("replay_view.load_collection", side_effect=FileNotFoundError("missing artifact")):
            app.run()
            require(not app.exception and bool(app.error), "Missing replay must show a recoverable error")
        app.sidebar.radio(key="courtvision_season_intelligence_view").set_value("Teams").run()
        app.sidebar.selectbox(key="courtvision_season_intelligence_season").select(CURRENT_SEASON).run()
        with patch("update_intelligence.load_update_status", return_value={"pipelines": {"teams": {
                "checkedAt": "2020-01-01T00:00:00+00:00", "status": "failed", "gamesThrough": None}}}):
            app.run()
            check_render(app)
            require(any("failed" in warning.value.lower() for warning in app.warning),
                    "Failed refresh must warn without hiding published data")
        with patch("update_intelligence.load_update_status", return_value={"pipelines": {"teams": {
                "checkedAt": "2020-01-01T00:00:00+00:00", "status": "success", "gamesThrough": None}}}):
            app.run()
            check_render(app)
            require(any("over a day old" in warning.value for warning in app.warning),
                    "Stale successful refresh must warn")
        app.sidebar.radio(key="courtvision_season_intelligence_view").set_value("Player Career").run()
        check_render(app)
        print("PASS: unavailable replay recovery and failed-refresh warning with published data retained")

        second = AppTest.from_file(str(entrypoint_path), default_timeout=90).run()
        check_render(second)
        require(second.sidebar.selectbox(
            key="courtvision_season_intelligence_season").value == CURRENT_SEASON,
            "A new session inherited the previous season")
        require(second.sidebar.radio(
            key="courtvision_season_intelligence_view").value == "Teams",
            "A new session inherited the previous view")
        require(app.sidebar.radio(
            key="courtvision_season_intelligence_view").value == "Player Career",
            "New session changed the original session")

        require(network.call_count == 0, f"Unexpected network attempts: {network.call_count}")
        require(workers.call_count == 0, f"Unexpected subprocess attempts: {workers.call_count}")
        print("PASS: independent session defaults; zero feed requests and worker launches")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrypoint", default="dashboard/app.py")
    args = parser.parse_args()
    validate_model()
    validate_published_app(args.entrypoint)
