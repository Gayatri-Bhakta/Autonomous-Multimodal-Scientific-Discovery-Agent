"""Week 3 adapter: extract_chart_information (src/ingestion/chart_reader.py)."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from src.frontend.services.common import ServiceResult
from src.frontend.utils.files import safe_filename

_FRIENDLY = {
    "ImageValidationError": ("invalid_image", "This image cannot be used"),
    "ChartConfigError": ("config", "The vision model is not configured"),
    "ModelAPIError": ("api_error", "The vision API call failed"),
    "InvalidModelResponse": ("invalid_response", "The model replied, but not with usable chart data"),
}


def read_chart(data: bytes, filename: str, client: Optional[Any] = None) -> ServiceResult:
    """Send one uploaded image to the vision model and return the validated extraction dict."""
    try:
        from src.ingestion import chart_reader
    except Exception as exc:
        return ServiceResult(False, message=f"Chart reader unavailable: {type(exc).__name__}: {exc}", code="backend_missing")
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / safe_filename(filename)
        path.write_bytes(data)
        try:
            extraction = chart_reader.extract_chart_information(str(path), client=client)
        except chart_reader.ChartReaderError as exc:
            code, prefix = _FRIENDLY.get(type(exc).__name__, ("chart_error", "Chart reading failed"))
            return ServiceResult(False, message=f"{prefix}: {exc}", code=code, seconds=time.monotonic() - started)
        except Exception as exc:
            return ServiceResult(False, message=f"Unexpected error: {type(exc).__name__}: {exc}", code="unexpected",
                                 seconds=time.monotonic() - started)
    return ServiceResult(True, data=extraction, message="Chart read.", seconds=time.monotonic() - started)


def points_dataframe(extraction: Dict[str, Any]) -> pd.DataFrame:
    """Data points as a table. Only rows with a numeric y are kept; x may be text (categories)."""
    rows = [{"series": p.get("series") or "(unnamed)", "x": p.get("x"), "y": p.get("y"),
             "reading": p.get("reading_type")} for p in extraction.get("data_points", []) if p.get("y") is not None]
    return pd.DataFrame(rows, columns=["series", "x", "y", "reading"])


def explanation(extraction: Dict[str, Any]) -> str:
    """Plain-language explanation built only from fields the model returned (no extra LLM call)."""
    x, y = extraction.get("x_axis", {}), extraction.get("y_axis", {})

    def axis(a: Dict[str, Any]) -> str:
        label = a.get("label") or "unlabelled"
        return f"{label} ({a['unit']})" if a.get("unit") else label

    lines = [f"This is a **{extraction.get('chart_type', 'unknown')}** chart"
             + (f" titled *{extraction['chart_title']}*." if extraction.get("chart_title") else "."),
             f"The x-axis shows **{axis(x)}** and the y-axis shows **{axis(y)}**."]
    if extraction.get("trend_summary"):
        lines.append(f"**Trend:** {extraction['trend_summary']}")
    if extraction.get("evidence"):
        lines.append("**Visual evidence:** " + "; ".join(extraction["evidence"]))
    if extraction.get("uncertainties"):
        lines.append("**Uncertain or unreadable:** " + "; ".join(extraction["uncertainties"]))
    return "\n\n".join(lines)
