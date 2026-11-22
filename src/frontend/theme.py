"""Dark research-dashboard styling. Static CSS only (no user text is ever injected here)."""
import streamlit as st

CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
h1, h2, h3 {letter-spacing: -0.01em;}
.hero {background: linear-gradient(135deg, #1B2033 0%, #2A2560 100%); border: 1px solid #2E3550;
       border-radius: 16px; padding: 1.6rem 1.8rem; margin-bottom: 1.2rem;}
.hero h1 {margin: 0 0 .3rem 0; font-size: 1.9rem;}
.hero p {margin: 0; color: #B9BED2;}
.card {background: #161B26; border: 1px solid #262D40; border-radius: 14px; padding: 1rem 1.1rem; height: 100%;}
.card .label {color: #8E95AD; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em;}
.card .value {font-size: 1.5rem; font-weight: 650; margin: .15rem 0;}
.card .caption {color: #8E95AD; font-size: .82rem;}
.badge {display: inline-block; padding: .12rem .6rem; border-radius: 999px; font-size: .75rem; font-weight: 600;}
.badge.ok {background: #12351F; color: #5BE08A;} .badge.warn {background: #3A2F10; color: #F5C451;}
.badge.err {background: #3B1518; color: #FF7A85;} .badge.muted {background: #232A3B; color: #A4ABC2;}
section[data-testid="stSidebar"] {border-right: 1px solid #262D40;}
div[data-testid="stExpander"] {border-radius: 12px;}
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
