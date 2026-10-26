"""Offline local CPU baseline, NOT Community Cloud capacity certification."""

import json
import platform
import resource
import statistics
import time
from unittest.mock import patch

from live_snapshot_cache import LiveSnapshotCache
from offline_live_sample import load_cpu_artifacts, sample_analysis


def main():
    with patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected HTTP')):
        started=time.perf_counter()
        artifacts=load_cpu_artifacts()
        load_seconds=time.perf_counter()-started
        cache=LiveSnapshotCache(ttl=300,max_age=300)
        started=time.perf_counter()
        result=sample_analysis(artifacts,cache)
        cold=time.perf_counter()-started
        warm=[]
        for _ in range(3):
            started=time.perf_counter()
            sample_analysis(artifacts,cache)
            warm.append(time.perf_counter()-started)
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mib=rss/(1024*1024) if platform.system()=='Darwin' else rss/1024
    print(json.dumps(dict(scope='Local offline CPU, archived 2OT, single caller; excludes browser/network/import startup',
        platform=platform.platform(),python=platform.python_version(),modelLoadSeconds=load_seconds,
        coldAnalysisSeconds=cold,warmAnalysisSeconds=warm,warmMedianSeconds=statistics.median(warm),
        processPeakMiB=mib,states=len(result.predictions)),indent=2))


if __name__=='__main__': main()
