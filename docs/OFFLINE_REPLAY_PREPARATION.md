# Offline historical replay preparation

## Autonomous Mac expansion

`src/run_replay_expansion.py` is a separate low-priority LaunchAgent, defined in
`deploy/com.courtvision.replay-expansion.plist`. It does not modify the existing
nightly intelligence or historical backfill agents. On the configured Mac it
runs at login, every 30 minutes while awake, and at 1:30 a.m. local time.
Publication eligibility uses America/Los_Angeles explicitly; missed publication
catches up on the next invocation after 1:30 a.m. Pacific. Sleep does not process
games; wake/login resumes from the saved queue. No ChatGPT execution is needed.

Each run attempts at most five completed games, one season at a time, with a
180-second subprocess timeout, single-thread CPU-library settings, background
priority, no overlap and a daily cap of 200 attempts. Frozen model and season
context are reused within each batch. A 2 GB free-space guard stops safely.
Only local processed PBP, box, impact, training and model inputs qualify.
Missing-input games wait for normal backfill; unchanged invalid games are skipped;
timed-out/interrupted work retries with an hour cooldown. 2024–25 is explicitly
paused until its systemic opening-state issue has a separately tested fix.

Prepared artifacts/queue live under `results/.runtime/replay-expansion/`, outside
the user Git index. Once nightly (or next wake), publication clones latest remote
main, merges validated immutable artifacts, rebuilds/audits the whole index and
pushes only replay artifacts/index/health by non-force push. Concurrent Git
changes cause a fresh-clone retry after one hour; no user files are staged or
reset. Git authentication must remain available in the logged-in Mac account.
One initial `--publish-now` can verify setup without waiting overnight.

The hosted Update health panel shows the last published expansion snapshot, not
live Mac liveness. Local authoritative state: `state.json`, `last-batch.log`,
`launchd.log`, `launchd-error.log` in that runtime directory. Publication failure
stays local until a successful push; the hosted timestamp then remains old.

To pause: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.courtvision.replay-expansion.plist`.
To resume: bootstrap that same plist. Do not remove active prepared artifacts or
change published history. No acquisition or permanent Live activation is added.

Hosted playback reads validated JSON only. It never fetches play-by-play or runs
the model. The original frozen V7 pipeline runs on the operator's Mac instead.

Use a clean latest-main release checkout for publication, keeping the active
source checkout and its backfill datasets untouched. Existing saved analysis
exports still use `batch_export_replays.py`. For a saved invalid analysis or
missing impact summary, `rebuild_saved_replays.py` can rerun the original offline
pipeline in a temporary directory. It never replaces the source cache.

To prepare a completed game without a saved analysis, add `--from-catalog`:

```sh
PYTHONPATH=src /path/to/python src/rebuild_saved_replays.py \
  --root /path/to/clean-release \
  --cache-root /Users/sahilnayak/Courtvision \
  --season 2025-26 --from-catalog --game-id 0022501200
```

Each invocation accepts at most five explicit distinct game IDs. Catalog mode
requires published, paired completed-game identities. Local processed/raw PBP,
season training context, frozen model/scaler and cached box scores are required.
Existing impact summaries are reused; missing ones are built by the original
offline attribution pipeline into temporary output. Remote PBP/record fallback
is explicitly prohibited. No scheduler or background worker is installed.

The exporter and rebuilder share an exclusive lock. Already published artifacts
are validated and skipped; differing published history is never overwritten.
Per-season reports are under `results/.runtime/replay-rebuild/`. Each game is
independently validated before publication; failures remain unavailable. Do not
clamp missing probabilities or fabricate player impact to make a game pass.

Before publishing, validate every indexed artifact with `load_catalog_replay`,
run the focused replay tests, and stage only the new artifacts, index and scoped
tooling/docs. Publish via non-force push; preserve active datasets and user index.
The app automatically discovers prepared artifacts from the published index.

Known limitation: the 2024–25 local processed inputs can produce missing opening
probabilities even after rerunning the unchanged pipeline. These remain blocked
pending a separately validated input/pipeline diagnosis. Current-season games
without local inputs require a separate acquisition workflow; this tool does not
claim to prepare them or provide complete season coverage automatically.
