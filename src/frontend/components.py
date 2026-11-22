"""Reusable UI pieces. Every dynamic string is HTML-escaped before it reaches unsafe_allow_html."""
from __future__ import annotations

import html
from typing import Dict, Optional

import streamlit as st

from src.frontend.services.common import ServiceResult
from src.frontend.utils import state

BADGES = {
    "ready": ("Ready", "ok"), "done": ("Done", "ok"), "loaded": ("Evidence loaded", "ok"),
    "needs_config": ("Needs config", "warn"), "todo": ("Not run yet", "muted"),
    "adapter_pending": ("Adapter pending", "warn"), "pending_backend": ("Backend not connected", "warn"),
    "preview_only": ("Preview only", "warn"),
    "module_missing": ("Module not found", "err"), "import_error": ("Import error", "err"), "failed": ("Failed", "err"),
}


def badge(key: str) -> str:
    label, tone = BADGES.get(key, (key, "muted"))
    return f'<span class="badge {tone}">{html.escape(label)}</span>'


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="hero"><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>',
                unsafe_allow_html=True)


def card(label: str, value: str, caption: str = "") -> None:
    st.markdown(f'<div class="card"><div class="label">{html.escape(label)}</div>'
                f'<div class="value">{html.escape(value)}</div><div class="caption">{html.escape(caption)}</div></div>',
                unsafe_allow_html=True)


def show_result(res: ServiceResult) -> None:
    """Success / warning / error banner for a service result."""
    if res.ok:
        st.success(res.message or "Done.")
    else:
        st.error(res.message or "Something went wrong.")
    for warning in res.warnings:
        st.warning(warning)


def not_connected(week: str, module: str, found: bool, needs: str) -> None:
    st.warning(f"**{week} backend is not connected to the frontend yet.** "
               + (f"`{module}` exists in this project, but " if found else f"`{module}` was not found, and ")
               + f"its public functions have not been inspected, so no adapter was written. {needs}")


def workflow_steps() -> None:
    """Progress bar + step list built from real session state."""
    status = state.workflow_status()
    steps = [("literature", "Literature review"), ("hypothesis", "Hypothesis generation"),
             ("charts", "Chart interpretation"), ("experiment", "Experiment execution"),
             ("paper", "Paper generation"), ("report", "Reports")]
    done = sum(1 for k, _ in steps if status[k] in ("done", "loaded"))
    st.progress(done / len(steps), text=f"{done} of {len(steps)} workflow steps completed")
    cols = st.columns(len(steps))
    for col, (key, label) in zip(cols, steps):
        col.markdown(f"**{html.escape(label)}**<br>{badge(status[key])}", unsafe_allow_html=True)


def logic_tree_dot() -> str:
    """Graphviz source of the workflow, coloured by real step status."""
    status = state.workflow_status()
    colour = {"done": "#1F7A43", "loaded": "#1F7A43", "failed": "#9B2C35", "todo": "#3A4157", "pending_backend": "#8A6D1E"}
    nodes = {"literature": "Literature", "hypothesis": "Hypotheses", "charts": "Charts", "experiment": "Experiment",
             "paper": "Paper", "report": "Reports"}
    lines = ["digraph G {", 'rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fontcolor=white, color="#262D40", fontname="Helvetica"];']
    for key, label in nodes.items():
        lines.append(f'{key} [label="{label}", fillcolor="{colour.get(status[key], "#3A4157")}"];')
    edges = [("literature", "hypothesis"), ("hypothesis", "experiment"), ("experiment", "paper"), ("charts", "paper"),
             ("literature", "paper"), ("paper", "report")]
    lines += [f"{a} -> {b};" for a, b in edges] + ["}"]
    return "\n".join(lines)


def trace_table() -> None:
    trace = st.session_state.get("trace") or []
    if not trace:
        st.info("No agent runs yet in this session.")
        return
    st.dataframe(trace, width="stretch", hide_index=True)
