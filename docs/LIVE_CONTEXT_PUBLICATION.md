# Inactive pregame-context publication tool

`src/published_live_context.py` builds a versioned JSON artifact offline. It is
not imported by the dashboard and is not added to the nightly job or its Git
publication allowlist. Hosted Live remains disabled. This is the publication
contract/tooling, not a verified production current-season data source.

Input is one JSON object with schemaVersion=1, season, seasonType="Regular
Season", completeThrough (ISO calendar date), scheduleSource, resultsSource,
scheduleVerification, schedule and results. Verification includes scope="full-season",
verified=true and timezone-aware checkedAt. These must be supplied by a trusted
operator/source adapter after independently verifying the whole schedule, never
inferred from completed-game discovery or the latest observed game date.

Each schedule entry has season, seasonType, ten-digit NBA gameId, gameDate,
homeTeamId and awayTeamId. Each result repeats those fields plus final=true,
homeScore and awayScore (nonnegative integers, no ties). Scores supply both
teams' outcomes consistently. IDs, dates and teams must match the schedule.
Duplicate games, preseason, unfinished results, unknown teams and every missing
scheduled result through completeThrough refuse publication. Rescheduled games
must have updated canonical dates; unresolved earlier games conservatively block
the artifact. Full-season coverage remains an upstream trust assertion: this
tool cannot detect an omitted schedule game without an independent source.

Only games on completeThrough + one day receive pregame contexts. Same-day and
future results never affect those records. Current-season smoothing is reused
unchanged; displayed raw W–L remains separate. Validated opening-night empty
history is distinct from missing results.

Run explicitly from the repo with PYTHONPATH=src:

```sh
.venv/bin/python src/published_live_context.py --source /absolute/verified-input.json --output /absolute/context-v1.json
```

Use a single publisher (the existing nightly job has a lock, but this standalone
tool does not). Validation completes before atomic replacement; failed refreshes
retain the last file, and coverage regression/season changes at the same path
are rejected. Use separate paths for each season. Atomic local replacement is
not Git publication, authenticity verification, or multi-writer serialization.
Consumers must still reject stale coverage for their target game; do not show an
old context as current. No production artifact is included because no full
2026–27 schedule source has yet been independently verified for this pipeline.

Next: implement and verify the upstream full-schedule acquisition/attestation,
then add this artifact to the locked nightly publication allowlist and a strict
hosted reader. Identity mapping, more captured fixtures, cache integration,
native ESPN box scores and actual-host resource checks remain separate gates.
