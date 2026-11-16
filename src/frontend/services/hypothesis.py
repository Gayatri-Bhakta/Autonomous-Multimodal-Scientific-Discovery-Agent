"""Week 2 adapter: HypothesisGenerator.generate_grounded (src/agents/hypothesis_agent.py)."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.frontend.services.common import ServiceResult
from src.frontend.utils.files import safe_filename


def parse_chunks(data: bytes, filename: str) -> ServiceResult:
    """Read an uploaded .json/.jsonl chunk file with the backend's own load_chunks()."""
    try:
        from src.agents.hypothesis_agent import load_chunks, normalize_chunks
    except Exception as exc:
        return ServiceResult(False, message=f"Hypothesis backend unavailable: {type(exc).__name__}: {exc}", code="backend_missing")
    suffix = Path(filename).suffix.lower()
    if suffix not in (".json", ".jsonl"):
        return ServiceResult(False, message="Evidence files must be .json or .jsonl.", code="invalid_upload")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / ("chunks" + suffix)
        path.write_bytes(data)
        try:
            chunks = load_chunks(str(path))
        except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
            return ServiceResult(False, message=f"Could not read '{safe_filename(filename)}' as JSON: {exc}", code="invalid_upload")
    if not isinstance(chunks, list) or not chunks:
        return ServiceResult(False, message="The file must contain a non-empty list of paper chunks.", code="invalid_upload")
    evidence, skipped = normalize_chunks(chunks)
    if not evidence:
        return ServiceResult(False, message="No usable chunks: each needs a paper id and some text.", code="invalid_upload", warnings=skipped)
    return ServiceResult(True, data=chunks, warnings=skipped)


def summarize_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per paper (merging several chunks of the same paper) for display."""
    from src.agents.hypothesis_agent import normalize_chunks

    evidence, _ = normalize_chunks(chunks)
    papers: Dict[str, Dict[str, Any]] = {}
    for chunk in evidence:
        row = papers.setdefault(chunk.paper_id, {"paper_id": chunk.paper_id, "title": chunk.title, "chunks": 0, "characters": 0})
        row["chunks"] += 1
        row["characters"] += len(chunk.searchable_text())
        row["title"] = row["title"] or chunk.title
    return list(papers.values())


def generate(chunks: List[Dict[str, Any]], topic: str, max_hypotheses: int = 3,
             require_verbatim_quotes: bool = True, llm: Optional[Any] = None) -> ServiceResult:
    """Run grounded generation. ``ok`` is True when at least one hypothesis passed validation."""
    try:
        from src.agents.hypothesis_agent import HypothesisGenerator
    except Exception as exc:
        return ServiceResult(False, message=f"Hypothesis backend unavailable: {type(exc).__name__}: {exc}", code="backend_missing")
    started = time.monotonic()
    try:
        generator = HypothesisGenerator(llm=llm, max_hypotheses=max_hypotheses,
                                        require_verbatim_quotes=require_verbatim_quotes)
        report = generator.generate_grounded(chunks, topic=topic.strip() or None)
    except Exception as exc:  # the backend returns safe results; this is a last resort
        return ServiceResult(False, message=f"Unexpected error: {type(exc).__name__}: {exc}", code="unexpected",
                             seconds=time.monotonic() - started)
    seconds = time.monotonic() - started
    ok = report.status in ("ok", "partial")
    message = {"ok": "Hypotheses generated and validated.",
               "partial": "Some hypotheses failed validation and were rejected (see details).",
               "insufficient_evidence": "; ".join(report.errors) or "Insufficient evidence.",
               "failed": "; ".join(report.errors) or "Generation failed."}[report.status]
    return ServiceResult(ok, data=report, message=message, code=report.status, seconds=seconds, warnings=list(report.notes))


def hypothesis_to_paper_text(h: Dict[str, Any]) -> str:
    """Editable draft text for the paper's hypothesis field (taken from the validated hypothesis)."""
    return f"{h['title']}. {h['problem_statement']} {h['proposed_solution']} Falsifiable test: {h['falsifiable_metric']}"
