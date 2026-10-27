"""Inactive hosted analysis join; frozen model/features stay unchanged."""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from cloud_espn_adapter import ProviderContextUnavailable
from cloud_live_bundle import get_live_bundle
from daily_live_context import read_day_context
from feature_engineering import add_live_model_features
from live_analysis import predict_live_probabilities
from live_game_date import eligible_game_date, overnight_game


@dataclass
class LiveAnalysis:
    snapshot: object
    predictions: object
    pregame_context: dict
    display_state: str


def analyze_live_snapshot(cache, canonical, context_path, loader, artifacts, progress=None, *, as_of_date=None):
    """Gate context before HTTP/inference. as_of_date is for deterministic replay tests.

    Caller owns bounded network loader, shared cache/tracker and immutable model
    artifacts. Production callers omit as_of_date and use bounded date eligibility.
    This entry point is not wired into any dashboard or worker.
    """
    now = datetime.now(ZoneInfo('America/New_York'))
    if (canonical['gameDate'] != as_of_date if as_of_date is not None
            else not eligible_game_date(canonical['gameDate'], now)):
        raise ProviderContextUnavailable('Live analysis requires eligible scheduled-date context')
    mapped = read_day_context(context_path, canonical)
    verified = {**canonical, 'espnEventId': mapped['espnEventId']}
    def dated_loader():
        pair = loader()
        if as_of_date is None and overnight_game(canonical['gameDate'], now):
            state = pair['event']['competitions'][0]['status']['type']['state']
            if state not in ('in', 'post'):
                raise ProviderContextUnavailable('Previous-day game must have started')
        return pair
    snapshot = get_live_bundle(cache, verified, dated_loader, progress)
    context = mapped['pregameContext']
    featured = add_live_model_features(snapshot.timeline, context)
    model, scaler, device = artifacts
    predictions = predict_live_probabilities(featured, model, scaler, device)
    probabilities = predictions['winProbability']
    if len(predictions) != len(snapshot.timeline) or not probabilities.between(0, 1).all():
        raise ProviderContextUnavailable('Invalid live predictions')
    state = ('stale_snapshot' if snapshot.is_stale else
             'possibly_stalled' if snapshot.progress_state == 'possibly_stalled' else
             'progress_unknown' if snapshot.progress_state == 'unknown' else 'validated_snapshot')
    return LiveAnalysis(snapshot, predictions, context, state)
