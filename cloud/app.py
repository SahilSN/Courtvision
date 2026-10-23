"""Community Cloud entry point: published intelligence, closed during setup."""

import os
from pathlib import Path
import runpy
import sys

import streamlit as st

# Never allow a host setting to enable expensive live/historical analysis here.
os.environ["COURTVISION_DEPLOYMENT_PROFILE"] = "published"

# Public repositories default to public apps on Community Cloud. Keep data off
# the page until the operator has verified the host's private sharing settings.
# This setup latch is NOT authentication; access control belongs to the host.
if os.environ.get("COURTVISION_CLOUD_READY") != "1":
    st.set_page_config(page_title="Courtvision staging", page_icon="🏀")
    st.title("Courtvision")
    st.info("Staging setup is in progress. The dashboard is not available yet.")
    st.stop()

# Only a reviewed, short-lived deployment request can activate diagnostics.
# No viewer control, no recurring schedule, and no results in the app UI.
root = Path(__file__).resolve().parents[1]
if os.environ.get("COURTVISION_DISABLE_OPERATOR_PROBES") != "1":
    if str(root / "src") not in sys.path:
        sys.path.append(str(root / "src"))
    from host_live_diagnostic import run_requested_probe
    try:
        run_requested_probe(root / "cloud/live_probe_request.json", root / "results/.runtime/host-probes")
    except OSError:
        print("COURTVISION_HOST_PROBE runtime_unavailable", flush=True)

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"),
    run_name="__main__",
)
