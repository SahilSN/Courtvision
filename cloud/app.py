"""Community Cloud entry point: published intelligence, closed during setup."""

import os
from pathlib import Path
import runpy

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

runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py"),
    run_name="__main__",
)
