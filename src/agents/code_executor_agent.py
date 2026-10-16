"""
Code Executor Agent
Member 5 Deliverable

Turns a hypothesis into a Python experiment script, runs it, and returns
(code, output). The orchestrator calls generate_and_run_code().

Week 1 skeleton: the script is built from a baseline template (no LLM call yet).
The prompt template is ready for the LLM to be plugged in later, and the
subprocess runner will be replaced by a Docker sandbox in a later week.
"""

import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, Tuple

# ---------------------------------------------------------------------------
# Prompt template (to be sent to the LLM once an API key is set up)
# ---------------------------------------------------------------------------
CODE_EXECUTOR_PROMPT = """You are the Code Executor Agent in an autonomous scientific discovery system.

Hypothesis:
{hypothesis}

Task:
Write ONE self-contained Python script that tests this hypothesis.

Rules:
- Use only the Python standard library unless told otherwise.
- Set a random seed so results are reproducible.
- Compare a baseline against the proposed method over several trials.
- Print the average metric for each, then a final line: Metric delta: <number>
- Return only the code, with no explanations.
"""

# ---------------------------------------------------------------------------
# Baseline experiment script (used until the LLM is connected)
# __HYPOTHESIS__ is replaced with the hypothesis text.
# ---------------------------------------------------------------------------
BASELINE_SCRIPT = '''import random
import statistics

random.seed(42)
HYPOTHESIS = __HYPOTHESIS__

N_TRIALS = 30


def run_trial(use_method):
    """Simulated metric: the proposed method shifts the mean slightly."""
    score = random.gauss(100, 5)
    return score + 2 if use_method else score


baseline = [run_trial(False) for _ in range(N_TRIALS)]
method = [run_trial(True) for _ in range(N_TRIALS)]

print(HYPOTHESIS)
print("Baseline mean:", round(statistics.mean(baseline), 3))
print("Method mean:", round(statistics.mean(method), 3))
print("Metric delta:", round(statistics.mean(method) - statistics.mean(baseline), 3))
'''


def build_prompt(hypothesis: str) -> str:
    """Fill the prompt template with the hypothesis."""
    return CODE_EXECUTOR_PROMPT.format(hypothesis=hypothesis.strip())


def generate_code(hypothesis: str) -> str:
    """Create a Python experiment script for the hypothesis.

    Later: send build_prompt(hypothesis) to the LLM and return its code.
    """
    return BASELINE_SCRIPT.replace("__HYPOTHESIS__", repr(hypothesis.strip()))


def run_code_detailed(code: str, timeout: int = 30) -> Dict[str, Any]:
    """Run the script in a separate process and return a structured result.

    Returns {"exit_code", "stdout", "stderr", "timed_out"}, the same shape the
    Docker sandbox runner returns, so the two are interchangeable (the debugger
    loop accepts either).
    Later: replace this with a Docker sandbox.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(code)
        path = f.name

    try:
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        def as_text(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")

        return {
            "exit_code": -1,
            "stdout": as_text(exc.stdout),
            "stderr": as_text(exc.stderr),
            "timed_out": True,
        }
    finally:
        os.remove(path)


def run_code(code: str, timeout: int = 30) -> str:
    """Run the script and return its output as a single string."""
    result = run_code_detailed(code, timeout)
    if result["timed_out"]:
        return f"Execution failed: timed out after {timeout} seconds."
    if result["exit_code"] != 0:
        return f"Execution failed (exit code {result['exit_code']}):\n{result['stderr'].strip()}"
    return result["stdout"].strip()


def generate_and_run_code(hypothesis: str) -> Tuple[str, str]:
    """Entry point used by src/orchestrator.py. Returns (code, output)."""
    code = generate_code(hypothesis)
    output = run_code(code)
    return code, output

class CodeExecutor:
    """Convenience class wrapper for generate_and_run_code."""

    @staticmethod
    def run(hypothesis: str) -> Tuple[str, str]:
        return generate_and_run_code(hypothesis)


if __name__ == "__main__":
    demo = "Dynamic token-level pruning reduces inference memory by 30% with <1% perplexity loss."
    code, output = generate_and_run_code(demo)
    print(output)
