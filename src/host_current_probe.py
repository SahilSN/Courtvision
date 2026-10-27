"""Bounded operator-only current-feed diagnostic; no activation or raw logs."""
from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from cloud_espn_adapter import normalize_snapshot
from cloud_espn_box import _normalize_box
from daily_live_context import read_day_context
from feature_engineering import add_live_model_features
from live_analysis import predict_live_probabilities
from live_refresh import current_event
from offline_live_sample import load_cpu_artifacts
from probe_live_access import fetch_json, BASE


def probe_current(day, environment):
    if day != datetime.now(ZoneInfo('America/New_York')).date().isoformat():
        return dict(status='wrong_day')
    root=Path(__file__).resolve().parents[1]
    path=root/'results/live_context'/ '2026-27_day_context_v1.json'
    stage='context'
    try:
        bundle=json.loads(path.read_text())
        if bundle['gameDate']!=day: raise ValueError('Wrong day')
        stage='scoreboard'
        board,_=fetch_json(BASE+'scoreboard?dates='+day.replace('-',''))
        active={str(e['id']) for e in board['events'] if e['status']['type']['state']=='in'}
        games=[g for g in bundle['games'] if g['espnEventId'] in active][:2]
        reports=[]
        artifacts=None
        for game in games:
            stage='context'
            try:
                mapped=read_day_context(path,game)
                stage='scoreboard_identity'
                event=current_event(game,mapped['espnEventId'],fetcher=lambda url:(board,{}))
                stage='summary'
                summary,_=fetch_json(BASE+'summary?event='+mapped['espnEventId'])
                stage='timeline'
                timeline=normalize_snapshot(event,summary,game)
                stage='box'
                _normalize_box(event,summary,game,timeline=timeline)
                stage='artifacts'
                if artifacts is None: artifacts=load_cpu_artifacts()
                stage='predictions'
                result=predict_live_probabilities(add_live_model_features(timeline,mapped['pregameContext']),*artifacts)
                if len(result)!=len(timeline) or not result.winProbability.between(0,1).all(): raise ValueError('Invalid predictions')
                reports.append(dict(gameId=game['gameId'],status='passed',states=len(result)))
            except Exception as error:
                reports.append(dict(gameId=game['gameId'],status='failed',stage=stage,errorType=type(error).__name__,
                                    causeType=type(error.__cause__).__name__ if error.__cause__ else None))
        return dict(status='current_checked',environment=environment,games=reports)
    except Exception as error:
        return dict(status='failed',stage=stage,errorType=type(error).__name__)
