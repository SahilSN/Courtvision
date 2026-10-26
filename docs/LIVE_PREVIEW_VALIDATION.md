# Gated offline Live UI preview

The new `cloud/live_preview.py` is a **separate local entry point**, disabled
unless COURTVISION_LOCAL_LIVE_PREVIEW=1. Community Cloud still runs cloud/app.py;
it does not import this page and hosted Live stays disabled. The preview gate
is not authentication and must not be treated as an access-control mechanism.

Run locally, binding loopback only:

```sh
COURTVISION_LOCAL_LIVE_PREVIEW=1 PYTHONPATH=src .venv/bin/python -m streamlit run cloud/live_preview.py --server.address 127.0.0.1 --server.port 8514
```

It uses the archived HOU@OKC two-overtime feed, actual frozen CPU artifacts and
synthetic opening-night verified context. A prominent dated banner says it is
offline, archived and contains full-game spoilers. No actual NBA/ESPN HTTP or
current-game discovery runs. State selection simulates unavailable/stale/stalled
conditions; it does not demonstrate a real provider outage. No fake current-game
status is shown. The cached sample result is copied before state simulations.

`live_preview_view.render_live_analysis` renders scores, separate raw pregame
records, solid blue/gold probability lines and traditional box tables. DNP and
missing stats remain distinguishable. Unavailable state has no estimates/table;
stale state explicitly says the snapshot is not current; possible-stall text
allows legitimate stoppages. Acquisition age and observed unchanged age are
separate. Advanced metrics are explicitly unavailable. Unknown state tokens do
not render a successful estimate. Per-game state/model/cache networking remains
outside the renderer.

Streamlit AppTest checks the default-disabled gate and all simulated states
with HTTP blocked. Browser verification confirmed the archived sample, 125–124
score, chart/box and stale warning on the narrow default viewport. Tables can
scroll horizontally; full accessibility/mobile certification is not claimed.

## Local performance baseline — October26,2026

`PYTHONPATH=src /tmp/courtvision-deploy-py312/bin/python src/benchmark_live_preview.py`
measured macOS27.0.1 ARM, Python3.12.2, one caller, archived594-state timeline:

- Frozen model/scaler load:1.204s.
- Cold analysis:0.659s.
- Three warm analyses:0.439s,0.201s,0.174s; median0.201s.
- Whole-process peak RSS:300.9MiB (includes imported runtime/model).

HTTP is blocked. Analysis timing includes fixture/context temporary-file IO,
normalization and inference; excludes Python imports/startup, browser rendering,
network and actual host concurrency. High-water RSS is not incremental pipeline
memory. This is NOT Streamlit Cloud cold-start, memory-limit or load evidence.
The benchmark makes no Git/data publication or app setting changes.

Actual Community Cloud whole-pipeline CPU/RAM/concurrency validation remains
pending. The earlier HTTP access probe does not establish those results. Before
Live rollout, use a separately bounded operator-host check (no repeated viewer
inference), inspect owner logs and remove activation afterward; do not enable
Live just because this offline/local preview passes.
