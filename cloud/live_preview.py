"""Local-only archived integration preview; not the Community Cloud entry point."""

import os
from pathlib import Path
import sys
import runpy

import streamlit as st

st.set_page_config(page_title='Courtvision · Live integration preview',page_icon='🏀',layout='wide')
if os.environ.get('COURTVISION_LOCAL_LIVE_PREVIEW') != '1':
    st.info('Local integration preview is disabled.')
    st.stop()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
render_live_analysis = runpy.run_path(str(Path(__file__).resolve().parents[1]/'src/live_preview_view.py'))['render_live_analysis']
from offline_live_sample import sample_analysis

st.caption('COURTVISION / GAME CENTER')
st.title('Houston at Oklahoma City')
st.warning('ARCHIVED OFFLINE SAMPLE · HOU @ OKC, October 21, 2025. Not a current live game. Full-game spoilers.')
with st.expander('Preview controls',expanded=False):
    state=st.selectbox('Preview state',['Validated snapshot','Unavailable','Stale snapshot','Possibly stalled'])
if state == 'Unavailable':
    render_live_analysis(None)
else:
    @st.cache_resource
    def archived_result():
        return sample_analysis()
    from copy import deepcopy
    result=deepcopy(archived_result())
    if state == 'Stale snapshot':
        result.display_state='stale_snapshot';result.snapshot.is_stale=True;result.snapshot.age_seconds=30
    elif state == 'Possibly stalled':
        result.display_state='possibly_stalled';result.snapshot.unchanged_seconds=125
    render_live_analysis(result,'OKC','HOU')
