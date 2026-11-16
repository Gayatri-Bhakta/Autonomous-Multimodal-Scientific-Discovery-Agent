"""Module and environment status for the Home page (booleans and names only, never secrets)."""
from __future__ import annotations

import importlib
import importlib.util
from typing import Any, Dict, List

from src.frontend.utils.env import code_execution_enabled, llm_status, vision_status

# (week, display name, module path, adapter implemented in the frontend?, needs LLM?, needs vision?)
MODULES = [
    ("Week 1", "Literature Reviewer", "src.agents.literature_agent", True, False, False),
    ("Week 2", "Hypothesis Generator", "src.agents.hypothesis_agent", True, True, False),
    ("Week 3", "Chart Interpreter (VLM)", "src.ingestion.chart_reader", True, False, True),
    ("Week 4", "Paper Synthesizer", "src.agents.synthesizer_agent", True, False, False),
    ("Executor", "Code Executor", "src.agents.code_executor_agent", True, False, False),
]


def _module_found(path: str) -> bool:
    try:
        return importlib.util.find_spec(path) is not None
    except (ImportError, ValueError, AttributeError):
        return False


def module_status() -> List[Dict[str, Any]]:
    llm, vision = llm_status(), vision_status()
    rows = []
    for week, name, path, adapter, needs_llm, needs_vision in MODULES:
        state, detail = "ready", "Connected."
        if not _module_found(path):
            state, detail = "module_missing", f"{path} was not found in this project."
        elif not adapter:
            state, detail = "adapter_pending", "Module present, but the frontend adapter is not connected yet."
        else:
            try:
                importlib.import_module(path)
            except Exception as exc:
                state, detail = "import_error", f"Import failed: {type(exc).__name__}."
            else:
                if week == "Executor":
                    detail = "Code preview connected; execution disabled (no secure sandbox)."
                if needs_llm and not llm["configured"]:
                    state, detail = "needs_config", "Set LLM_API_KEY and LLM_MODEL (see .env.example)."
                elif needs_vision and not vision["configured"]:
                    state, detail = "needs_config", "Set VLM_* / LLM_* variables with a vision-capable model."
        rows.append({"week": week, "name": name, "module": path, "state": state, "detail": detail})
    return rows


def latex_status() -> Dict[str, Any]:
    try:
        from src.utils.latex_compiler import find_engine

        engine = find_engine("pdflatex")
    except Exception:
        engine = None
    return {"available": engine is not None, "engine": "pdflatex" if engine else None}


def environment_status() -> Dict[str, Any]:
    return {"llm": llm_status(), "vision": vision_status(), "latex": latex_status(),
            "code_execution_enabled": code_execution_enabled()}


