"""Shared presentation for the published app; no data, model or activation logic."""

from html import escape
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st


def apply_shell():
    st.markdown('''<style>
    .stMainBlockContainer {max-width:1440px;padding-top:2.4rem;padding-bottom:3rem;}
    [data-testid="stSidebar"] {border-right:1px solid rgba(148,163,184,.13);}
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top:1rem;}
    [data-testid="stSidebar"] [role="radiogroup"] {gap:6px;}
    [data-testid="stSidebar"] [role="radiogroup"] label {border:1px solid transparent;border-radius:10px;padding:9px 11px;min-height:44px;}
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {background:rgba(148,163,184,.07);border-color:rgba(148,163,184,.18);}
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {background:rgba(73,164,255,.10);border-color:rgba(73,164,255,.3);}
    [data-testid="stSidebar"] [role="radiogroup"] label:focus-within {outline:2px solid #49a4ff;outline-offset:2px;}
    [data-testid="stMetric"] {border:1px solid rgba(148,163,184,.17);background:rgba(148,163,184,.035);border-radius:14px;padding:15px 18px;}
    [data-testid="stDataFrame"] {border:1px solid rgba(148,163,184,.14);border-radius:12px;overflow:hidden;}
    [data-baseweb="tab-list"] {gap:18px;border-bottom:1px solid rgba(148,163,184,.16);}
    [data-baseweb="tab"] {min-height:44px;}
    .cv-brand {display:flex;align-items:center;gap:11px;margin:3px 0 18px;}
    .cv-brand-mark {width:37px;height:37px;display:grid;place-items:center;background:#18314c;color:#83c6ff;border:1px solid #345474;border-radius:12px;font-size:12px;font-weight:800;letter-spacing:1px;}
    .cv-brand-name {font-size:21px;font-weight:750;letter-spacing:-.5px;}
    .cv-brand-note {font-size:11px;color:#9aa9bd;margin-top:2px;}
    .cv-page-head {margin:0 0 20px;border-bottom:1px solid rgba(148,163,184,.15);padding-bottom:21px;}
    .cv-eyebrow {font-size:11px;font-weight:650;letter-spacing:1.6px;color:#83bff5;text-transform:uppercase;}
    .cv-page-head h1 {font-size:clamp(1.8rem,4vw,2.6rem);line-height:1.15;letter-spacing:-1px;margin:8px 0 10px;padding:0;}
    .cv-page-head p {color:#a7b4c7;line-height:1.65;font-size:14px;margin:0;max-width:760px;}
    @media(max-width:640px) {.stMainBlockContainer{padding-top:1.4rem;padding-left:1rem;padding-right:1rem;}
    [data-testid="stMetric"]{padding:12px;} .cv-page-head{padding-bottom:17px;margin-bottom:16px;}}
    </style>''',unsafe_allow_html=True)


def sidebar_brand():
    st.sidebar.markdown('<div class="cv-brand"><div class="cv-brand-mark" aria-hidden="true">CV</div>'
                        '<div><div class="cv-brand-name">Courtvision</div>'
                        '<div class="cv-brand-note">NBA intelligence · Private beta</div></div></div>',unsafe_allow_html=True)


def page_heading(title, description, eyebrow='Courtvision Intelligence'):
    st.markdown(f'<header class="cv-page-head"><div class="cv-eyebrow">{escape(eyebrow)}</div>'
                f'<h1>{escape(title)}</h1><p>{escape(description)}</p></header>',unsafe_allow_html=True)


def feature_label(value):
    return {'Teams':'Team ratings','Players':'Player ratings','Player Career':'Player careers',
            'Replay Pilot':'Replay collection'}.get(value,value)


def workspace_label(value):
    return {'Season Intelligence':'Season Intelligence','Live Beta':'Live · Game Center'}.get(value,value)


def time_label(value):
    try:
        stamp=datetime.fromisoformat(value)
        if stamp.tzinfo is None:
            raise ValueError('Missing timezone')
        return stamp.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%b %d · %I:%M %p PT')
    except (ValueError,TypeError):
        return 'Unknown'
