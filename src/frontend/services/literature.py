"""Week 1 adapter: LiteratureReviewer (src/agents/literature_agent.py)."""
from __future__ import annotations

import time
from typing import Any

from src.frontend.services.common import ServiceResult


def review(topic: str, max_papers: int = 5, save: bool = True) -> ServiceResult:
    """Run the real literature reviewer and return structured paper analysis."""
    if not isinstance(topic, str) or not topic.strip():
        return ServiceResult(
            False, message="Please enter a research topic.", code="invalid_input"
        )

    if not isinstance(max_papers, int) or max_papers < 1:
        return ServiceResult(
            False, message="Maximum papers must be at least 1.", code="invalid_input"
        )

    started = time.monotonic()

    try:
        from src.agents.literature_agent import LiteratureReviewer

        reviewer = LiteratureReviewer()
        result = reviewer.review(
            topic.strip(),
            max_results=min(max_papers, 50),
            save=save,
        )

    except Exception as exc:
        return ServiceResult(
            False,
            message=f"Literature review failed: {type(exc).__name__}: {exc}",
            code="unexpected",
            seconds=time.monotonic() - started,
        )

    seconds = time.monotonic() - started

    if result.status != "ok":
        return ServiceResult(
            False,
            data=result,
            message=result.error or f"Literature review status: {result.status}",
            code=result.status,
            seconds=seconds,
        )

    return ServiceResult(
        True,
        data=result,
        message=f"Retrieved {len(result.papers)} research papers.",
        code="ok",
        seconds=seconds,
    )
