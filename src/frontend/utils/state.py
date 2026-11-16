"""Streamlit session-state helpers: shared results, run trace and workflow status."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import streamlit as st

OUTPUT_DIR = Path("output") / "frontend"

DEFAULTS: Dict[str, Any] = {
    "topic": "",
    "chunks": [],            # evidence chunks (dicts) used by the Hypothesis page
    "chunk_source": None,
    "hypothesis_report": None,   # GroundedReport (pydantic)
    "selected_hypothesis": None, # dict of one hypothesis chosen for the paper
    "chart_images": [],      # [{"name", "path"}]
    "chart_results": [],     # [{"name", "ok", "data"|"message", "seconds"}]
    "paper_build": None,     # {"synthesis": SynthesisResult, "compile": CompileResult|None}
    "paper_results_seed": None,
    "trace": [],             # run trace entries
    "uploads": [],           # uploaded document info
}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = list(value) if isinstance(value, list) else value


def add_trace(step: str, status: str, seconds: float = 0.0, detail: str = "", model: str = "") -> None:
    st.session_state["trace"].append({
        "time": datetime.now(timezone.utc).strftime("%H:%M:%S"), "step": step, "status": status,
        "seconds": round(float(seconds), 2), "model": model or "-", "detail": detail[:300]})


def add_upload(kind: str, name: str, size: int) -> None:
    uploads = st.session_state["uploads"]
    if not any(u["name"] == name and u["kind"] == kind for u in uploads):
        uploads.append({"kind": kind, "name": name, "size_kb": round(size / 1024, 1)})


def workflow_status() -> Dict[str, str]:
    """Per workflow step: done | loaded | failed | todo | preview_only."""
    s = st.session_state
    report = s.get("hypothesis_report")
    build = s.get("paper_build")
    charts = s.get("chart_results") or []
    paper = "todo"
    if build:
        comp = build.get("compile")
        paper = "done" if (comp is None or comp.pdf_ok or comp.fallback_files) else "failed"
    return {
        "literature": "loaded" if s.get("chunks") else "todo",
        "hypothesis": "todo" if report is None else ("done" if report.status in ("ok", "partial") else "failed"),
        "charts": "todo" if not charts else ("done" if any(c["ok"] for c in charts) else "failed"),
        "experiment": "preview_only" if s.get("experiment_code_preview") else "todo",
        "paper": paper,
        "report": "done" if (build or report or charts) else "todo",
    }
