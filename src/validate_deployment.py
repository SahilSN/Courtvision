"""Offline deployment smoke test; run from a clean checkout after installation.

Uses bundled artifacts only. No NBA calls, workers, or publication are allowed.
This checks app execution, not visual layout, browser assets, or load capacity.
"""

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


def validate_published_app():
    summaries, games, coverage = load_published_player_data()
    require(not summaries.empty and not games.empty, "Missing published player data")
    require(CURRENT_SEASON in set(coverage.season), "Current player season missing")
    for person_id in games.personId.unique():
        build_player_career(games, person_id)

    with patch.dict(os.environ, {"COURTVISION_DEPLOYMENT_PROFILE": "published"}), \
         patch("requests.sessions.Session.request", side_effect=AssertionError(
             "Published deployment attempted a network request")) as network, \
         patch("subprocess.Popen", side_effect=AssertionError(
             "Published deployment attempted a subprocess")) as workers:
        app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=90)
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

        second = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=90).run()
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
    validate_model()
    validate_published_app()
