"""Bounded operator-only current-feed diagnostic; no activation or raw logs."""
from datetime import datetime
import json
import runpy
from pathlib import Path
from zoneinfo import ZoneInfo

from cloud_espn_box import _normalize_box
from cloud_live_analysis import analyze_live_snapshot
from live_snapshot_cache import LiveSnapshotCache
from daily_live_context import read_day_context
from live_refresh import current_event
from offline_live_sample import load_cpu_artifacts
from probe_live_access import fetch_json, BASE
from reviewed_live_players import REVIEWED


def probe_current(day, environment):
    if day != datetime.now(ZoneInfo('America/New_York')).date().isoformat():
        return dict(status='wrong_day')
    root=Path(__file__).resolve().parents[1]
    path=root/'results/live_context'/ '2026-27_day_context_v1.json'
    stage='context'
    try:
        ready=runpy.run_path(str(root/'src/live_runtime_gate.py'))['runtime_ready'](root)
        if not ready:return dict(status='runtime_blocked',runtimeReady=False)
        bundle=json.loads(path.read_text())
        if bundle['gameDate']!=day: raise ValueError('Wrong day')
        stage='scoreboard'
        board,_=fetch_json(BASE+'scoreboard?dates='+day.replace('-',''))
        # Same-day completed games can validate coverage, but are not evidence
        # that four feeds are advancing simultaneously. Never analyze pregame.
        available={str(e['id']) for e in board['events'] if e['status']['type']['state'] in ('in','post')}
        games=[g for g in bundle['games'] if g['espnEventId'] in available and g['gameId'] in ('0022600120','0022600121','0022600122','0022600123')]
        reports=[]
        artifacts=None
        for game in games:
            stage='context'
            measure={'attempts':0}
            try:
                mapped=read_day_context(path,game)
                stage='scoreboard_identity'
                event=current_event(game,mapped['espnEventId'],fetcher=lambda url:(board,{}))
                stage='artifacts'
                if artifacts is None: artifacts=load_cpu_artifacts()
                def loader():
                    measure['attempts']+=1
                    summary,_=fetch_json(BASE+'summary?event='+mapped['espnEventId'])
                    return dict(event=event,summary=summary)
                stage='acquisition'
                result=analyze_live_snapshot(LiveSnapshotCache(),game,path,loader,artifacts)
                reports.append(dict(gameId=game['gameId'],status='passed',states=len(result.predictions),
                                    sourceState=event['status']['type']['state'],attempts=measure['attempts']))
            except Exception as error:
                reports.append(dict(gameId=game['gameId'],status='failed',stage=stage,errorType=type(error).__name__,
                                    attempts=measure['attempts'],
                                    causeType=type(error.__cause__).__name__ if error.__cause__ else None,
                                    reason={'An involved player needs a reviewed identity mapping':'identity_unresolved',
                                            'Play timeline is not reconciled to the header score':'score_header_lag',
                                            'ESPN box score unavailable or unreconciled':'box_unreconciled'}.get(str(error),'other_validation')))
        return dict(status='current_checked',environment=environment,games=reports,
                    runtimeReady=ready,
                    currentIdentityCode=any(row[2]=='Christian Anderson' for row in REVIEWED),
                    currentMinutesCode='minutesAvailable' in _normalize_box.__code__.co_consts)
    except Exception as error:
        return dict(status='failed',stage=stage,errorType=type(error).__name__)
