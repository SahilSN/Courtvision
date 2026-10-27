"""Presentation states from accepted source metadata, never from a zero clock."""


def verified_source_state(data):
    try:
        statuses = [data['event']['competitions'][0]['status']['type'],
                    data['summary']['header']['competitions'][0]['status']['type']]
        if all(s.get('state') == 'post' and s.get('completed') is True for s in statuses):
            return 'post'
        if all(s.get('state') == 'in' and s.get('completed') is False for s in statuses):
            return 'in'
    except (KeyError, IndexError, TypeError, AttributeError):
        pass
    return 'unknown'


def presentation_state(result):
    if result is None:
        return 'Unavailable'
    if result.display_state in ('stale_snapshot','possibly_stalled'):
        return 'Delayed'
    if result.display_state not in ('validated_snapshot','progress_unknown'):
        return 'Unavailable'
    return {'post':'Final','in':'Live'}.get(getattr(result.snapshot,'source_state','unknown'),'Snapshot')
