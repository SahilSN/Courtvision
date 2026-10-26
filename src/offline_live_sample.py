"""Explicit archived fixture harness, never a current live game."""

import json
from pathlib import Path
import tempfile

import joblib
import torch

from cloud_live_analysis import analyze_live_snapshot
from feature_engineering import MODEL_FEATURES
from live_snapshot_cache import LiveSnapshotCache
from model import WinProbabilityMLP

ROOT=Path(__file__).resolve().parents[1]


def sample_inputs():
    feed=json.loads((ROOT/'src/fixtures/espn_contract_0022500001.json').read_text())
    feed['summary']['boxscore']['players']=json.loads((ROOT/'src/fixtures/espn_box_0022500001.json').read_text())['players']
    game=feed['canonical']
    context=dict(homeTeamId=game['homeTeamId'],awayTeamId=game['awayTeamId'],homePreGameWins=0,homePreGameLosses=0,
                 awayPreGameWins=0,awayPreGameLosses=0,homePreGameWinPct=0.5,awayPreGameWinPct=0.5,strengthDifference=0.0)
    day=dict(schemaVersion=1,season=game['season'],seasonType='Regular Season',gameDate=game['gameDate'],
             completeThrough='2025-10-20',games=[{**game,'espnEventId':feed['event']['id'],'pregameContext':context}])
    return feed,day


def load_cpu_artifacts():
    model=WinProbabilityMLP(input_size=len(MODEL_FEATURES))
    model.load_state_dict(torch.load(ROOT/'models/win_probability_mlp_v7.pt',map_location='cpu',weights_only=True))
    model.eval()
    return model,joblib.load(ROOT/'models/win_probability_scaler_v7.pkl'),torch.device('cpu')


def sample_analysis(artifacts=None, cache=None):
    feed,day=sample_inputs()
    with tempfile.TemporaryDirectory(prefix='courtvision-offline-preview-') as directory:
        path=Path(directory)/'day.json'
        path.write_text(json.dumps(day))
        return analyze_live_snapshot(cache or LiveSnapshotCache(),feed['canonical'],path,lambda:feed,
            artifacts or load_cpu_artifacts(),as_of_date=feed['canonical']['gameDate'])
