"""Environment helpers. Only booleans and non-secret names are ever returned (never key values)."""
from __future__ import annotations

import os
from typing import Dict

SECRET_KEYS = ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "VLM_PROVIDER", "VLM_API_KEY",
               "VLM_MODEL", "VLM_BASE_URL", "GEMINI_API_KEY", "CHART_MAX_IMAGE_MB", "ENABLE_CODE_EXECUTION")


def load_environment() -> None:
    """Load .env (if python-dotenv is installed) and copy Streamlit secrets into os.environ."""
    try:
        from dotenv import load_dotenv

        load_dotenv(override=False)
    except ImportError:
        pass
    try:  # hosted platforms keep secrets in st.secrets
        import streamlit as st

        for key in SECRET_KEYS:
            if not os.environ.get(key) and key in st.secrets:
                os.environ[key] = str(st.secrets[key])
    except Exception:  # no secrets file / not running under Streamlit
        pass


def llm_status() -> Dict[str, object]:
    """Same rule as the backend: both LLM_API_KEY and LLM_MODEL must be set."""
    configured = bool(os.getenv("LLM_API_KEY")) and bool(os.getenv("LLM_MODEL"))
    return {"configured": configured, "provider": os.getenv("LLM_PROVIDER", "anthropic"),
            "model": os.getenv("LLM_MODEL") or None}


def vision_status() -> Dict[str, object]:
    """Reuses the Week 3 configuration reader; returns provider/model only."""
    try:
        from src.ingestion.chart_reader import ChartConfigError, vision_config_from_env
    except Exception as exc:
        return {"configured": False, "provider": None, "model": None, "problem": f"chart reader unavailable ({type(exc).__name__})"}
    try:
        cfg = vision_config_from_env(dict(os.environ))
    except ChartConfigError as exc:
        return {"configured": False, "provider": None, "model": None, "problem": str(exc)}
    return {"configured": True, "provider": cfg.provider, "model": cfg.model, "problem": None}


def code_execution_enabled() -> bool:
    return os.getenv("ENABLE_CODE_EXECUTION", "").strip().lower() in ("1", "true", "yes")
