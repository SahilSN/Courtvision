"""Inactive integration prototype: validate both panels before replacing raw cache."""

from dataclasses import dataclass
from copy import deepcopy

from cloud_espn_adapter import normalize_snapshot, validate_canonical
from cloud_espn_box import normalize_box
from live_snapshot_cache import SnapshotKey


@dataclass
class LiveBundle:
    timeline: object
    box: dict
    age_seconds: float
    is_stale: bool
    refresh_error_type: str = None


def get_live_bundle(cache, canonical, loader):
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
        box = normalize_box(data['event'], data['summary'], canonical)
        return timeline, box

    def validated_loader():
        data = deepcopy(loader())
        validate_pair(data)
        return data

    snapshot = cache.get(key, validated_loader)
    # Defensive reconstruction per caller; raw cache never holds DataFrames.
    timeline, box = validate_pair(snapshot.data)
    return LiveBundle(timeline, box, snapshot.age_seconds, snapshot.is_stale,
                      snapshot.refresh_error_type)
