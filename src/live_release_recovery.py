"""Controlled interruption test of a real validated pair, never a viewer route."""
from cloud_live_analysis import analyze_live_snapshot
from live_snapshot_cache import LiveSnapshotCache, SnapshotUnavailable


def verify_recovery(game, context_path, pair, artifacts):
    clock = [0.0]
    cache = LiveSnapshotCache(clock=lambda: clock[0])
    def join(loader):
        return analyze_live_snapshot(cache, game, context_path, loader, artifacts,
                                     as_of_date=game['gameDate'])
    def fail():
        raise TimeoutError('Controlled release diagnostic')
    first = join(lambda: pair)
    clock[0] = 16
    stale = join(fail)
    if stale.display_state != 'stale_snapshot':
        raise AssertionError('Retained pair was not marked stale')
    if not first.predictions.equals(stale.predictions):
        raise AssertionError('Stale predictions changed')
    for panel in ('players', 'teams'):
        if not first.snapshot.box[panel].equals(stale.snapshot.box[panel]):
            raise AssertionError('Stale box changed')
    clock[0] = 61
    try:
        join(fail)
    except SnapshotUnavailable:
        pass
    else:
        raise AssertionError('Expired snapshot remained available')
    clock[0] = 77
    recovered = join(lambda: pair)
    if recovered.snapshot.is_stale or not recovered.predictions.equals(first.predictions):
        raise AssertionError('Recovery did not restore the verified pair')
    return dict(status='passed', retainedPair=True, expiredUnavailable=True, recovered=True,
                scope='Controlled timeout/clock with a real validated feed; not an actual provider outage or browser test')
