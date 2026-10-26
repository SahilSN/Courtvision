"""Bounded process-local observations; an unchanged feed is a warning, not proof."""

from collections import OrderedDict
import hashlib
import json
from threading import RLock
import time


class FeedProgress:
    def __init__(self, threshold=120, max_entries=16, clock=time.monotonic):
        if threshold <= 0 or max_entries < 1:
            raise ValueError('Invalid progress limits')
        self.threshold, self.max_entries, self.clock = threshold, max_entries, clock
        self._states, self._lock = OrderedDict(), RLock()

    def observe(self, key, data):
        competition = data['summary']['header']['competitions'][0]
        status = competition['status']['type']
        # Only explicit in-progress play is eligible. Timeouts/intermission/final
        # do not imply an upstream stall; transition back starts a new window.
        active = status.get('state') == 'in' and status.get('name') == 'STATUS_IN_PROGRESS' and status.get('completed') is False
        relevant = {'plays': data['summary']['plays'], 'box': data['summary']['boxscore'],
                    'status': status, 'competitors': competition['competitors']}
        digest = hashlib.sha256(json.dumps(relevant, sort_keys=True, allow_nan=False).encode()).hexdigest()
        now = self.clock()
        with self._lock:
            previous = self._states.pop(key, None)
            since = previous[1] if previous and previous[0] == digest and previous[2] and active else now
            self._states[key] = (digest, since, active)
            while len(self._states) > self.max_entries:
                self._states.popitem(last=False)
        if not active:
            return 'not_active', None
        age = max(0, now - since)
        return ('possibly_stalled' if age >= self.threshold else 'observing'), age
