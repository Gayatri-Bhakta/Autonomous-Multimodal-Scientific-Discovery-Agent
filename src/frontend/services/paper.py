"""Week 4 adapter: SynthesizerAgent (src/agents/synthesizer_agent.py) + compile_with_fallback."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.frontend.services.common import ServiceResult


def parse_authors(text: str) -> List[Dict[str, Any]]:
    """One author per line: 'Name' or 'Name | Affiliation'."""
    authors = []
    for line in (text or "").splitlines():
        if line.strip():
            name, _, affiliation = line.partition("|")
            authors.append({"name": name.strip(), "affiliation": affiliation.strip() or None})
    return authors


def parse_lines(text: str) -> List[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def metas_from_chunks(chunks: List[Dict[str, Any]], ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Reference metadata (PaperMeta-compatible dicts) taken from evidence chunks, one per paper."""
    wanted = set(ids) if ids is not None else None
    metas: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        pid = next((str(chunk[k]) for k in ("paper_id", "arxiv_id", "pmid", "id") if chunk.get(k)), None)
        if not pid or not chunk.get("title") or (wanted is not None and pid not in wanted):
            continue
        if pid not in metas:
            meta = {k: chunk[k] for k in ("title", "authors", "year", "published", "url", "doi", "venue", "journal")
                    if chunk.get(k)}
            meta["paper_id"] = pid
            metas[pid] = meta
    return list(metas.values())


def build_paper(data: Dict[str, Any], output_dir: Path, use_llm: bool = True, compile_pdf: bool = True,
                llm: Optional[Any] = None, basename: str = "generated_research_paper") -> ServiceResult:
    """Validate input, write .tex/.bib, optionally compile. Never claims a PDF unless one exists."""
    try:
        from src.agents import synthesizer_agent as sa
        from src.utils.latex_compiler import compile_with_fallback
    except Exception as exc:
        return ServiceResult(False, message=f"Paper backend unavailable: {type(exc).__name__}: {exc}", code="backend_missing")
    started = time.monotonic()
    try:
        agent = sa.SynthesizerAgent(llm=llm, use_env_llm=use_llm and llm is None)
        synthesis = agent.synthesize(data, output_dir=output_dir, basename=basename, require_llm=use_llm)
    except sa.InputValidationError as exc:
        return ServiceResult(False, message=f"Please fix the input: {exc}", code="invalid_input", seconds=time.monotonic() - started)
    except sa.SynthesizerConfigError as exc:
        return ServiceResult(False, message=str(exc), code="config", seconds=time.monotonic() - started)
    except sa.SynthesizerError as exc:
        return ServiceResult(False, message=f"Synthesis failed: {exc}", code="synthesis_failed", seconds=time.monotonic() - started)
    except Exception as exc:
        return ServiceResult(False, message=f"Unexpected error: {type(exc).__name__}: {exc}", code="unexpected",
                             seconds=time.monotonic() - started)
    compiled = None
    if compile_pdf:
        try:
            compiled = compile_with_fallback(synthesis.tex_path, synthesis.bib_path)
        except Exception as exc:  # the compiler reports problems as results; this is a last resort
            return ServiceResult(False, data={"synthesis": synthesis, "compile": None}, code="compile_crash",
                                 message=f"Paper written, but compilation crashed: {type(exc).__name__}: {exc}",
                                 seconds=time.monotonic() - started, warnings=list(synthesis.warnings))
    return ServiceResult(True, data={"synthesis": synthesis, "compile": compiled},
                         message=f"Paper draft written ({synthesis.status}).", code=synthesis.status,
                         seconds=time.monotonic() - started, warnings=list(synthesis.warnings))
