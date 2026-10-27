# Historical Replay: independent completed-game catalog

Historical Replay is a separate top-level workspace, available even with Live
disabled or its rollout expired. Completed 2026–27 games belong in this archive,
not in a “historical live replay” branch. Live retains only its guarded current
game window and its existing scheduled/in-game/final presentation. The archived
workspace never uses Live context, feed refreshes, a Live cache or Live model
resources. Its health footer remains read-only operational evidence.

The old nested Replay Pilot selection migrates to Historical Replay. Intelligence
keeps Team ratings, Player ratings and Player careers. The full local legacy
dashboard's existing discovery/replay behavior is not removed by this release.

## What the catalog means

- Season, team, date and preparation-state filters browse published completed
  regular-season team-game metadata. Each game requires a matching home/away
  pair, one date, reciprocal teams and a season-consistent NBA regular-season ID.
  Scheduled, in-progress and one-sided records are not advertised as completed.
- **Not prepared** means catalog metadata exists, but no full replay is published.
  Team/player intelligence backfill completion is NOT replay preparation.
- **Prepared** means an artifact is indexed. Opening it verifies its digest,
  identity, schema, model label, numeric timeline, final scores, both teams' box
  points and required panels. Missing/changed/invalid artifacts fail closed;
  there is no Live fallback or guessed estimate. A corrupt index does not erase
  completed-game metadata or declare games ready.
- All replay panels remain precomputed FULL-GAME SPOILERS. Timeline inspection
  and exact-event jumps are not spoiler-free playback. Both team lines stay solid.
- Current-season metadata defaults to 2026–27 even when no replay is prepared.
  The initial catalog has 43 published current-season completed games and zero
  ready current-season replays. It has SIX ready 2025–26 games: the four original
  validated exports plus two newly exported from trusted final local caches.
  These counts are release evidence, not promises of complete NBA coverage.

## Offline operator preparation

`results/replay_catalog/index_v1.json` lists scoped artifact identities and SHA256
digests. Original pilot JSONs remain unchanged. New artifacts live in
`results/replay_catalog/games/<NBA_GAME_ID>.json` and require explicit
`completed:true` and `seasonType:"Regular Season"`. The legacy exception is
restricted to the four already reviewed pilot IDs, not arbitrary new files.
Paths cannot escape the designated roots; reads and metadata sizes are bounded.

From a clean release checkout with dependencies installed:

```sh
PYTHONPATH=src .venv/bin/python src/prepare_replay_catalog.py \
  --root /absolute/path/to/clean-release-checkout \
  --cache-root /absolute/path/to/trusted-local-Courtvision \
  --season 2026-27 --game-id 0022600001
```

That ID is an example, not a claim its replay is ready. The command requires
existing final `v1_v7` analysis, matching box-score and WPA caches for every
selected game. It does NOT fetch games or run inference. Only use Courtvision's
own trusted caches: pickle decoding is restricted to this explicit offline build
tool, never uploaded files or hosted requests. Select at most20 distinct games
per batch. All selected exports must validate before files are exposed. Existing
different prepared files are not overwritten. New complete files publish before
the index, which is atomically replaced only after validation; interruption can
leave unindexed new files, never a ready placeholder or altered old replay.

Rebuild the index only:

```sh
PYTHONPATH=src .venv/bin/python src/replay_catalog.py --root /absolute/path/to/clean-release-checkout
```

Publish reviewed new JSONs/index and scoped code with a normal non-force push.
Do not stage the active worker checkout or reset its data/index. The nightly
intelligence publisher does not publish or overwrite this independent archive.
Do not add every cached game blindly or run preparation inside Streamlit.

## Next stages (not implemented here)

### Resumable export of caches already on the Mac

```sh
PYTHONPATH=src .venv/bin/python src/batch_export_replays.py \
  --root /absolute/path/to/clean-release-checkout \
  --cache-root /absolute/path/to/trusted-local-Courtvision \
  --limit 20 --max-seconds 60
```

This discovers only named existing `v1_v7/*_top3.pkl` caches; it does not acquire
or analyze missing games. It uses an exclusive lock and atomic per-game ledger
at `results/.runtime/replay-export/status.json`. Already indexed artifacts are
validated and skipped. Missing input files are reported separately. Failed caches
are retried only if an input fingerprint changes or `--retry-blocked` is supplied.
Each game is independently staged and fully validated before exposure; one bad
game does not stop other exports. The time budget is checked between games, not
hard cancellation of in-flight file decoding. Rerun the same command to resume;
no background scheduler is installed. Publish only scoped new JSONs and index
from a clean checkout, preserving active data and the user index.

The first actual run found27 saved analyses:6 already prepared,16 newly exported,
4 rejected for invalid probabilities and1 missing a WPA summary. All22 published
artifacts pass the catalog validator. No2026–27 final analysis caches were present.
Local on-demand analysis capability does not imply every game is already cached.
The four invalid probability histories must be investigated, not clamped,
silently dropped or relabeled as verified. A missing impact file must come from
the validated attribution pipeline, not zeros or an older incompatible summary.

Produce missing current-season final analysis caches through a separately
validated offline acquisition workflow, then export batches. Add independent
resume/coverage accounting and storage/publication appropriate to a large replay
archive before expanding to entire seasons. No new scheduler, unlimited cache
scan, automatic replay backfill, Live archive switch or external storage service
is created by this first catalog release.
