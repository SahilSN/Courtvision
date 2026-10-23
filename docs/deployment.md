# Published Intelligence deployment

## Scope

The first hosting profile is an explicitly labeled, read-only Intelligence beta.
It includes Team, Player, and covered-game Career Intelligence across the bundled
seasons. Partial historical coverage remains labeled. It does not expose Live,
historical game analysis, or replay, and launches no Player Impact worker.

The default remains `full`: existing local navigation, model, live, and historical
behavior are unchanged. A misspelled profile fails startup instead of silently
enabling the full app. This profile is a feature boundary, not authentication.

## Runtime and clean installation

Use Python **3.12** with a current pip for new deployments. Do not replace the
existing local virtual environment or the Mac scheduler's interpreter in place.
The audit's fresh Python 3.10.0 installation hit a SciPy native-library import
failure even though installation and `pip check` succeeded. Changing Python
alone did not fix it. `requirements-deployment.txt` selects the official,
SHA-256-pinned macOS 12 ARM64 wheel for the same SciPy version on CPython 3.12;
other platforms retain the original version pin. Native imports,
serialized model loading, and UI execution are therefore required checks.

From a clean checkout, create a new environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
# Optional on Linux: install the pinned CPU-only PyTorch wheel first.
.venv/bin/python -m pip install -r requirements-deployment.txt
.venv/bin/python -m pip check
PYTHONPATH=src .venv/bin/python -m unittest discover -s src -p 'test_*.py'
.venv/bin/python src/validate_deployment.py
```

The Deployment checks workflow performs a clean Python 3.12 installation on
Linux and macOS and executes these regressions. The Linux job installs the pinned
PyTorch CPU artifact referenced by `cloud/requirements.txt`.
The SciPy wheel workaround and loader error are documented in the
[upstream issue](https://github.com/scipy/scipy/issues/25635) and the official
[release artifact listing](https://pypi.org/project/scipy/1.15.3/).
Direct dependencies are pinned; transitive dependencies are not fully locked.
CI is a verification gate, not a claim that arbitrary future resolutions work.

The smoke test uses bundled model/CSV artifacts, checks all published season
views and career aggregation, verifies session defaults, and fails on feed or
subprocess attempts. It is not a visual, security, capacity, or browser-asset test.

## Start the beta

Set `COURTVISION_DEPLOYMENT_PROFILE=published` in the hosting service environment.
Choose Python 3.12 in that service's build/runtime settings. Start command:

```bash
COURTVISION_DEPLOYMENT_PROFILE=published .venv/bin/python -m streamlit run dashboard/app.py --server.headless=true --server.address=0.0.0.0
```

Configure the service's required port through its supported environment/start
settings. Leave Streamlit's default request protections enabled. For local-only
staging use `--server.address=127.0.0.1` instead. Nothing in this repository
creates a hosting account or publishes a public URL.

## Streamlit Community Cloud setup

Use repository `SahilSN/Courtvision`, branch `main`, entry point `cloud/app.py`,
and Python 3.12 in Advanced settings. Dependencies are discovered from
`cloud/requirements.txt`, which includes the deployment requirements and pins
the Linux CPU-only PyTorch build. The wrapper always selects published
intelligence, regardless of a conflicting host profile setting.

The cloud entry point initially displays only a setup notice, with no dashboard
data or game-analysis imports. **Do not set `COURTVISION_CLOUD_READY` yet.** This
is a deployment setup latch, not an authentication mechanism.

Because this repository is public, verify the app's actual sharing settings
before enabling data. Select **Only specific people can view this app** in
Community Cloud's sharing settings and verify an unauthenticated browser cannot
access it. If private sharing is unavailable, leave setup closed and choose a
host/access-control solution with the user; do not assume a secret URL is private.
See the official [sharing settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).

Only after privacy is verified, add this root-level string to the app's Secrets
settings, which Community Cloud exposes as an environment variable:

```toml
COURTVISION_CLOUD_READY = "1"
```

Do not commit secrets files. Do not copy GitHub tokens or Mac scheduler credentials
to this app; it reads committed artifacts and does not run the updater.
The setup notice is expected until that readiness flag is explicitly enabled.

The cloud requirements use a hash-pinned official CPU wheel rather than adding a
second package index, so Community Cloud's uv resolver does not shadow unrelated
PyPI packages. Arrow is pinned to 24.0.0, matching the host's safety replacement
for the Arrow 25 series observed during deployment. Community Cloud also manages
its own pip/certificate-package updates; its final environment can differ from
the local environment despite direct dependency pins.

Staging was deployed on October 23, 2026 at
<https://bucpjmvcsl28fxcedurbyj.streamlit.app/>. Sharing is restricted to specific
people, with no additional viewer invitations sent. A fresh unauthenticated
HTTP session followed redirects through Streamlit authentication before the
setup latch was enabled. Team, Player, and Career views were verified in the
signed-in browser. This is staging, not a public production release.

The app tracks `main`. Git-triggered updates are configured by Community Cloud;
the first real overnight data publication still requires end-to-end confirmation.

Offline cloud-wrapper regression:

```bash
.venv/bin/python src/validate_deployment.py --entrypoint cloud/app.py
```

## Nightly publication must reach the host

1. The Mac LaunchAgent runs once at 1 a.m. local time, with wake/login catch-up.
   It must have internet and working Git authentication. It updates current-season
   Team and Player Intelligence independently, retaining valid data on failure.
2. Its isolated publication pushes the allowlisted current-season artifacts and
   health JSON to `main`. Historical backfill publication is a separate operation.
3. Configure and verify a host Git-triggered redeploy or an explicit artifact sync
   when those data files change. GitHub publication does **not** refresh an
   existing server checkout by itself. Do not add another hourly/cloud updater.
4. Confirm the deployed commit, games-through date, and last successful check in
   the app after a real nightly publication. The app has 30-second reader caches;
   these cannot compensate for files that never reached the host.

If publication or host ingestion fails, preserve the last valid published files,
inspect Mac logs/health and host deployment logs, restore access, and retry the
nightly command if needed. Failed games remain eligible for a later update.
Do not rewrite the last successful timestamp to hide stale data.

Mac logs: `results/.runtime/nightly/updates.log` and `status.json`. Shared published
health: `results/season_intelligence/2026-27_update_status_v1.json`. See README for
install, manual-run, and disable commands. Never expose private Git credentials
or local logs as public assets.

## Before public release

- Require successful deployment checks on the release commit and verify the
  same runtime/dependencies on the selected host.
- Stage the published profile, exercise concurrent browser sessions and restart
  recovery, check resource use, and confirm partial/stale/failed-data notices.
- Verify that a real Mac publication reaches the host without manual intervention.
- Decide public access, privacy/data-use terms, monitoring, and abuse controls.

Full-feature cloud hosting is a separate milestone: provision historical runtime
data/storage, verify NBA endpoints from that host, and harden worker ownership,
queue limits, and cache concurrency before exposing expensive game analysis.
