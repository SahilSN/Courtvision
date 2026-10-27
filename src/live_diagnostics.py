"""Throttled operator-only diagnostics: no raw feed, errors or user identifiers."""
from collections import OrderedDict
import json
import math
import re
from threading import RLock
import time


def _emit(message):
    print(message,flush=True)


class RefreshDiagnostics:
    def __init__(self,clock=time.monotonic,emit=_emit,max_entries=16,interval=60):
        self.clock,self.emit,self.max_entries,self.interval=clock,emit,max_entries,interval
        self.states=OrderedDict();self.lock=RLock()

    def record(self,game_id,state,seconds,age=None,error_type=None):
        if not re.fullmatch(r'002\d{7}',str(game_id)) or state not in {
                'scheduled','unavailable','paused','stale_snapshot','possibly_stalled','progress_unknown','validated_snapshot'}:
            return False
        if not math.isfinite(seconds) or seconds<0 or (age is not None and (not math.isfinite(age) or age<0)):
            return False
        with self.lock:
            now=self.clock();previous=self.states.pop(game_id,None)
            count=previous[2]+1 if previous else 1
            if previous and previous[0]==state and now-previous[1]<self.interval:
                self.states[game_id]=(state,previous[1],count)
                return False
            self.states[game_id]=(state,now,0)
            while len(self.states)>self.max_entries: self.states.popitem(last=False)
            report=dict(gameId=game_id,state=state,refreshSeconds=round(seconds,3),samples=count)
            if age is not None: report['snapshotAgeSeconds']=round(age,1)
            if error_type and re.fullmatch(r'[A-Za-z_]{1,64}',error_type): report['errorType']=error_type
            try:
                self.emit('COURTVISION_LIVE_STATE '+json.dumps(report,allow_nan=False))
            except (OSError,ValueError):
                return False
            return True


diagnostics=RefreshDiagnostics()
