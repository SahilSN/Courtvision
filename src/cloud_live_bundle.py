"""Inactive integration prototype: validate both panels before replacing raw cache."""

from dataclasses import dataclass
from copy import deepcopy
import time

from cloud_espn_adapter import normalize_snapshot, validate_canonical, ScoreSectionsUnreconciled
from cloud_espn_box import _normalize_box
from live_snapshot_cache import SnapshotKey
from live_diagnostics import coherence_diagnostics
from live_game_state import verified_source_state

SCORE_RETRY_ATTEMPTS = 2
SCORE_RETRY_DELAY = 0.5
SCORE_RETRY_BUDGET = 8.0


@dataclass
class LiveBundle:
    timeline: object
    box: dict
    age_seconds: float
    is_stale: bool
    refresh_error_type: str = None
    progress_state: str = 'unknown'
    unchanged_seconds: float = None
    verified_at: str = None
    max_age_seconds: float = 60
    source_state: str = 'unknown'


def get_live_bundle(cache, canonical, loader, progress=None):
    """Caller owns shared cache, verified canonical context, and bounded I/O loader.

    Invalid/lagging box or timeline never replaces the last jointly valid value.
    Snapshot age is acquisition age, NOT evidence the upstream feed is progressing.
    Neither this prototype nor its raw cache is wired into the app.
    """
    canonical = deepcopy(canonical)
    validate_canonical(canonical)
    key = SnapshotKey('espn', canonical['gameId'], canonical['season'],
                      'Regular Season', canonical['gameDate'], 'joint-box-v1')

    def validate_pair(data):
        if canonical.get('espnEventId') is not None and str(data['event']['id']) != str(canonical['espnEventId']):
            raise ValueError('Snapshot differs from verified ESPN event mapping')
        timeline = normalize_snapshot(data['event'], data['summary'], canonical)
        box = _normalize_box(data['event'], data['summary'], canonical, timeline=timeline)
        return timeline, box

    def validated_loader():
        started=time.monotonic()
        for attempt in range(SCORE_RETRY_ATTEMPTS):
            data = deepcopy(loader())
            try:
                validate_pair(data)
            except ScoreSectionsUnreconciled as error:
                reason = ('timeline_header' if str(error) == 'Play timeline is not reconciled to the header score'
                          else 'box_points')
                coherence_diagnostics.observe(canonical['gameId'], reason)
                # Only the single-flight cache owner retries. Identity, malformed
                # data and transport failures never create a retry loop. The
                # budget is checked between bounded calls, not hard cancellation.
                if attempt+1>=SCORE_RETRY_ATTEMPTS or time.monotonic()-started+SCORE_RETRY_DELAY>=SCORE_RETRY_BUDGET:
                    raise
                time.sleep(SCORE_RETRY_DELAY)
                if time.monotonic()-started>=SCORE_RETRY_BUDGET:raise
            else:
                coherence_diagnostics.observe(canonical['gameId'], None)
                return data

    snapshot = cache.get(key, validated_loader)
    # Defensive reconstruction per caller; raw cache never holds DataFrames.
    timeline, box = validate_pair(snapshot.data)
    progress_key = (key, canonical['homeTeamId'], canonical['awayTeamId'], snapshot.data['event']['id'])
    state, age = progress.observe(progress_key, snapshot.data) if progress is not None else ('unknown', None)
    return LiveBundle(timeline, box, snapshot.age_seconds, snapshot.is_stale,
                      snapshot.refresh_error_type, state, age, snapshot.verified_at, cache.max_age,
                      verified_source_state(snapshot.data))
