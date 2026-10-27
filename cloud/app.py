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
from ui_shell import apply_shell, sidebar_brand, workspace_label
apply_shell()
sidebar_brand()


def render_health_footer():
    st.sidebar.divider()
    try:
        runpy.run_path(str(root/'src/deployment_health_view.py'))['render_health'](root)
    except Exception:
        st.sidebar.caption('Update health temporarily unavailable.')

games=()
# Historical Replay is an independent offline route, not a Live replay mode.
# Migrate the old nested replay selection before any sidebar widgets are built.
if st.session_state.get('courtvision_season_intelligence_view')=='Replay Pilot':
    st.session_state['cloud_workspace']='Historical Replay'
    st.session_state['courtvision_season_intelligence_view']='Teams'
if st.session_state.get('cloud_workspace')=='Live Beta' and os.environ.get('COURTVISION_ENABLE_LIVE_BETA')=='1' and os.environ.get('COURTVISION_DISABLE_LIVE_BETA')!='1':
    try:
        import importlib
        importlib.invalidate_caches()
        from daily_live_policy import active_games
        games=active_games(root,os.environ)
        if games:
            runtime_gate=runpy.run_path(str(root/'src/live_runtime_gate.py'))['runtime_ready']
            if not runtime_gate(root):
                print('COURTVISION_LIVE_RUNTIME blocked stale_or_unavailable_validators',flush=True)
                games=()
    except Exception as error:
        # Optional rollout policy must not break the default dashboard during a hot deployment.
        print('COURTVISION_LIVE_POLICY unavailable '+type(error).__name__,flush=True)
live_unavailable=not games and st.session_state.get('cloud_workspace')=='Live Beta'
if live_unavailable:
    st.session_state['cloud_workspace']='Season Intelligence'
workspace=st.sidebar.radio('Workspace',['Season Intelligence','Live Beta','Historical Replay'],key='cloud_workspace',format_func=workspace_label)
if live_unavailable:
    st.sidebar.info('Live is not available in the current beta window. Use Historical Replay to browse completed games.')
if workspace=='Historical Replay':
    st.set_page_config(page_title='Courtvision · Historical Replay',page_icon='🏀',layout='wide')
    runpy.run_path(str(root/'src/replay_view.py'))['render_replay_view'](root)
    render_health_footer()
    st.stop()
if games:
    if workspace=='Live Beta':
        st.set_page_config(page_title='Courtvision · Live beta',page_icon='🏀',layout='wide')
        try:
            view=runpy.run_path(str(root/'src/live_beta_view.py'))
            view['render_live_beta'](root,games,rollout_guard=lambda:
                active_games(root,os.environ) if runtime_gate(root) else ())
        except Exception as error:
            print('COURTVISION_LIVE_VIEW unavailable '+type(error).__name__,flush=True)
            st.warning('Live is temporarily unavailable. Return to Season Intelligence in the sidebar.')
        render_health_footer()
        st.stop()

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"),
    run_name="__main__",
    init_globals={'CLOUD_SHELL':True},
)
render_health_footer()
