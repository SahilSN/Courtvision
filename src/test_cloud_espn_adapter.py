from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import joblib
import pandas as pd
import torch

from cloud_espn_adapter import normalize_snapshot, verified_pregame_context, ProviderContextUnavailable
from feature_engineering import MODEL_FEATURES, add_live_model_features
from live_analysis import predict_live_probabilities
from model import WinProbabilityMLP
from nba_api.stats.static import players
from espn_live import fetch_espn_live_play_by_play, normalize_name
from preprocess import preprocess_live_game


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "src/fixtures/espn_contract_0022500001.json"


class CloudAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())

    def normalize(self, fixture=None):
        f = fixture or self.fixture
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Unexpected network")):
            return normalize_snapshot(f["event"], f["summary"], f["canonical"])

    def test_captured_overtime_feed_reconciles_without_nba_requests(self):
        timeline = self.normalize()
        self.assertTrue(timeline.elapsedGameTime.is_monotonic_increasing)
        self.assertEqual(int(timeline.period.max()), 6)
        self.assertEqual((int(timeline.scoreHome.iloc[-1]), int(timeline.scoreAway.iloc[-1])), (125, 124))
        self.assertEqual(int(timeline.homeTeamId.iloc[-1]), 1610612760)
        # This real feed's corrected sequence numbers cannot be used as clock order.
        sequences = [int(p["sequenceNumber"]) for p in self.fixture["summary"]["plays"]]
        self.assertNotEqual(sequences, sorted(sequences))

    def test_adapter_matches_existing_normalization_on_the_same_fixture(self):
        f = self.fixture
        game = f["canonical"]
        competition = f["summary"]["header"]["competitions"][0]
        mapping = {str(c["team"]["id"]): {"team_id": game[c["homeAway"] + "TeamId"],
            "team_tricode": "OKC" if c["homeAway"] == "home" else "HOU", "side": c["homeAway"]} for c in competition["competitors"]}
        names = {}
        for player in players.get_players():
            names.setdefault(normalize_name(player["full_name"]), set()).add(player["id"])
        def resolve(name, team_id, season):
            matches = names.get(normalize_name(name), set())
            return next(iter(matches)) if len(matches) == 1 else None
        with patch("requests.sessions.Session.request", side_effect=AssertionError("Network forbidden")), \
             patch("espn_live.resolve_espn_event", return_value={"event_id": f["event"]["id"], "team_map": mapping}), \
             patch("espn_live.fetch_espn_summary", return_value=f["summary"]), \
             patch("espn_live.resolve_nba_person_id", side_effect=resolve):
            legacy = preprocess_live_game(fetch_espn_live_play_by_play(game["gameId"], game["gameDate"], game["season"]))
        adapted = self.normalize()
        pd.testing.assert_frame_equal(adapted[legacy.columns], legacy, check_flags=False)

    def test_wrong_game_season_type_date_and_teams_are_rejected(self):
        for defect in ("event", "season", "type", "date", "teams"):
            f = deepcopy(self.fixture)
            if defect == "event":
                f["summary"]["header"]["id"] = "1"
            elif defect == "season":
                f["event"]["season"]["year"] += 1
            elif defect == "type":
                f["event"]["season"]["type"] = 1
            elif defect == "date":
                f["canonical"]["gameDate"] = "2025-10-22"
            else:
                f["canonical"]["homeTeamId"], f["canonical"]["awayTeamId"] = f["canonical"]["awayTeamId"], f["canonical"]["homeTeamId"]
            with self.subTest(defect=defect), self.assertRaises(ProviderContextUnavailable):
                self.normalize(f)

    def test_duplicate_scrambled_or_unreconciled_play_data_is_rejected(self):
        for defect in ("duplicate", "order", "score", "empty"):
            f = deepcopy(self.fixture)
            if defect == "duplicate":
                f["summary"]["plays"].append(f["summary"]["plays"][0])
            elif defect == "order":
                f["summary"]["plays"].reverse()
            elif defect == "empty":
                f["summary"]["plays"] = []
            else:
                f["summary"]["header"]["competitions"][0]["competitors"][0]["score"] = "999"
            with self.subTest(defect=defect), self.assertRaises(ProviderContextUnavailable):
                self.normalize(f)

    def test_unknown_participant_is_not_zero_impact(self):
        f = deepcopy(self.fixture)
        f["summary"]["plays"][0]["participants"][0]["athlete"]["id"] = "unmapped"
        with self.assertRaisesRegex(ProviderContextUnavailable, "reviewed identity"):
            self.normalize(f)

    def test_partial_snapshot_uses_only_present_plays(self):
        f = deepcopy(self.fixture)
        f["summary"]["plays"] = f["summary"]["plays"][:100]
        last = f["summary"]["plays"][-1]
        competition = f["summary"]["header"]["competitions"][0]
        competition["status"]["type"]["completed"] = False
        for team in competition["competitors"]:
            team["score"] = str(last["homeScore"] if team["homeAway"] == "home" else last["awayScore"])
        t = self.normalize(f)
        self.assertEqual(int(t.period.max()), 1)
        self.assertLess(t.elapsedGameTime.max(), 720)
        self.assertNotIn("homeWin", t.columns)

    def test_frozen_v7_cpu_inference_on_captured_adapter_output(self):
        timeline = self.normalize()
        context = verified_pregame_context(self.fixture["canonical"],
            pd.DataFrame(columns=["season", "gameId", "gameDate", "team", "teamWin"]),
            pd.DataFrame([{**self.fixture["canonical"], "seasonType": "Regular Season"}]),
            complete_through="2025-10-20", history_season_type="Regular Season")
        featured = add_live_model_features(timeline, context)
        model = WinProbabilityMLP(input_size=len(MODEL_FEATURES))
        model.load_state_dict(torch.load(ROOT / "models/win_probability_mlp_v7.pt", map_location="cpu", weights_only=True))
        model.eval()
        scaler = joblib.load(ROOT / "models/win_probability_scaler_v7.pkl")
        output = predict_live_probabilities(featured, model, scaler, torch.device("cpu"))
        self.assertTrue(output.winProbability.between(0, 1).all())
        self.assertEqual(len(output), len(timeline))

    def test_missing_scores_and_invalid_clocks_fail_instead_of_becoming_zero(self):
        for defect in ("score", "clock"):
            f = deepcopy(self.fixture)
            if defect == "score":
                del f["summary"]["plays"][0]["homeScore"]
            else:
                f["summary"]["plays"][0]["clock"]["displayValue"] = "13:00"
            with self.subTest(defect=defect), self.assertRaises(ProviderContextUnavailable):
                self.normalize(f)


class VerifiedPregameTest(unittest.TestCase):
    def setUp(self):
        self.game = {"gameId": "0022600001", "season": "2026-27", "gameDate": "2026-10-23",
                     "homeTeamId": 1610612760, "awayTeamId": 1610612745}
        self.schedule = pd.DataFrame([
            {"gameId": "0022600002", "gameDate": "2026-10-21", "homeTeamId": 1610612760, "awayTeamId": 1610612747},
            {"gameId": "0022600003", "gameDate": "2026-10-22", "homeTeamId": 1610612745, "awayTeamId": 1610612760},
            {"gameId": "0022600001", "gameDate": "2026-10-23", "homeTeamId": 1610612760, "awayTeamId": 1610612745}])
        self.schedule["season"], self.schedule["seasonType"] = "2026-27", "Regular Season"
        self.history = pd.DataFrame([
            {"gameId": "0022600002", "gameDate": "2026-10-21", "team": "OKC", "teamWin": 1},
            {"gameId": "0022600003", "gameDate": "2026-10-22", "team": "OKC", "teamWin": 1},
            {"gameId": "0022600003", "gameDate": "2026-10-22", "team": "HOU", "teamWin": 0},
            {"gameId": "0022600001", "gameDate": "2026-10-23", "team": "OKC", "teamWin": 0}])
        self.history["season"] = "2026-27"

    def context(self, **kwargs):
        return verified_pregame_context(self.game, self.history, self.schedule,
            complete_through=kwargs.get("complete_through", "2026-10-22"), history_season_type=kwargs.get("history_season_type", "Regular Season"))

    def test_real_records_exclude_target_day_and_reuse_current_smoothing(self):
        result = self.context()
        self.assertEqual((result["homePreGameWins"], result["homePreGameLosses"]), (2, 0))
        self.assertEqual((result["awayPreGameWins"], result["awayPreGameLosses"]), (0, 1))
        self.assertAlmostEqual(result["homePreGameWinPct"], 0.75)
        self.assertAlmostEqual(result["awayPreGameWinPct"], 1 / 3)

    def test_missing_prior_game_and_stale_catalog_do_not_become_neutral(self):
        with self.assertRaises(ProviderContextUnavailable):
            self.context(complete_through="2026-10-21")
        self.history = self.history.iloc[1:]
        with self.assertRaises(ProviderContextUnavailable):
            self.context()

    def test_preseason_mixed_season_and_duplicate_sources_fail(self):
        with self.assertRaises(ProviderContextUnavailable):
            self.context(history_season_type="Pre Season")
        self.history = pd.concat([self.history, self.history.iloc[[0]]])
        with self.assertRaises(ProviderContextUnavailable):
            self.context()

    def test_wrong_record_dates_or_catalog_season_fail(self):
        self.history.loc[0, "gameDate"] = "2026-10-20"
        with self.assertRaises(ProviderContextUnavailable):
            self.context()
        self.history.loc[0, "gameDate"] = "2026-10-21"
        self.schedule["season"] = "2025-26"
        with self.assertRaises(ProviderContextUnavailable):
            self.context()
