# Offline historical replay preparation

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
