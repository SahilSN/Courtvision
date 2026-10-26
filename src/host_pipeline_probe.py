"""Fixed-size archived CPU workload for a single expiring operator request."""

import platform
import resource
import time

from live_snapshot_cache import LiveSnapshotCache
from offline_live_sample import load_cpu_artifacts, sample_analysis


def probe_pipeline(day, environment):
    started=time.perf_counter()
    artifacts=load_cpu_artifacts()
    model_seconds=time.perf_counter()-started
    cache=LiveSnapshotCache(ttl=300,max_age=300)
    timings=[]
    for _ in range(3):  # Fixed bound: one cold and two warm calls, no HTTP.
        started=time.perf_counter()
        result=sample_analysis(artifacts,cache)
        timings.append(round(time.perf_counter()-started,4))
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak=rss/(1024*1024) if platform.system()=='Darwin' else rss/1024
    passed=model_seconds<30 and max(timings)<10 and peak<900
    return dict(status='pipeline_baseline_passed' if passed else 'pipeline_budget_exceeded',
        environment=environment,scope='Archived fixed-size CPU workload only; not current-feed/concurrency certification',
        modelLoadSeconds=round(model_seconds,4),analysisSeconds=timings,processPeakMiB=round(peak,1),
        states=len(result.predictions),python=platform.python_version())
