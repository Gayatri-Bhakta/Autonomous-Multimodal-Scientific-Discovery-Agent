"""Safe code-preview adapter for the experiment page.

This service generates code only. It never executes generated code.
"""
from __future__ import annotations

import time

from src.frontend.services.common import ServiceResult


def generate_preview(hypothesis: str) -> ServiceResult:
    """Generate an experiment script without executing it."""
    if not isinstance(hypothesis, str) or not hypothesis.strip():
        return ServiceResult(
            False,
            message="Please enter a research hypothesis.",
            code="invalid_input",
        )

    if len(hypothesis) > 2000:
        return ServiceResult(
            False,
            message="Hypothesis must be 2000 characters or fewer.",
            code="invalid_input",
        )

    started = time.monotonic()

    try:
        from src.agents.code_executor_agent import generate_code

        code = generate_code(hypothesis.strip())

        return ServiceResult(
            True,
            data={"code": code},
            message="Experiment code generated. It has NOT been executed.",
            code="preview_only",
            seconds=time.monotonic() - started,
        )

    except Exception as exc:
        return ServiceResult(
            False,
            message=f"Code generation failed: {type(exc).__name__}: {exc}",
            code="generation_error",
            seconds=time.monotonic() - started,
        )
