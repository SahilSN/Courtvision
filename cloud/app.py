"""Community Cloud entry point: published intelligence, closed during setup."""

import os
from pathlib import Path
import runpy
import sys

import streamlit as st

# Keep legacy full/live/historical discovery disabled regardless of host settings.
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
if (root / "cloud/live_probe_request.json").exists() and os.environ.get("COURTVISION_DISABLE_OPERATOR_PROBES") != "1":
    if str(root / "src") not in sys.path:
        sys.path.append(str(root / "src"))
    try:
        import importlib
        importlib.invalidate_caches()
        diagnostic = runpy.run_path(str(root / "src/host_live_diagnostic.py"))
        diagnostic["run_requested_probe"](root / "cloud/live_probe_request.json", root / "results/.runtime/host-probes")
    except Exception as error:
        # Diagnostics are optional and must never block the published dashboard,
        # including during a hot deployment's transient source-file updates.
        print("COURTVISION_HOST_PROBE unavailable " + type(error).__name__, flush=True)

if str(root/'src') not in sys.path:
    sys.path.append(str(root/'src'))
from live_rollout import allowed_games
games=allowed_games(root/'cloud/live_rollout.json',os.environ)
if games:
    workspace=st.sidebar.radio('Workspace',['Season Intelligence','Live Beta'],key='cloud_workspace')
    if workspace=='Live Beta':
        st.set_page_config(page_title='Courtvision · Live beta',page_icon='🏀',layout='wide')
        try:
            view=runpy.run_path(str(root/'src/live_beta_view.py'))
            view['render_live_beta'](root,games,rollout_guard=lambda:allowed_games(root/'cloud/live_rollout.json',os.environ))
        except Exception as error:
            print('COURTVISION_LIVE_VIEW unavailable '+type(error).__name__,flush=True)
            st.warning('Live is temporarily unavailable. Return to Season Intelligence in the sidebar.')
        st.stop()
else:
    # A killed/expired rollout must not strand a viewer in its previous selection.
    st.session_state['cloud_workspace']='Season Intelligence'

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"),
    run_name="__main__",
)
