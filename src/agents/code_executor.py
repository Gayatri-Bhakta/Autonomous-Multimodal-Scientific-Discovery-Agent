"""CodeExecutor agent: validate, approve and sandbox-run experiment code.

SECURITY MODEL (read this first)
================================
* Static validation (``validate_code``) is a *safety net, NOT a sandbox*. Python
  code can always find ways around AST checks. It only rejects obviously
  dangerous code early and gives clear error messages.
* A plain ``subprocess`` running ``python`` on the host is NOT secure and this
  module never does that. Experiment code is executed ONLY inside a separate
  Docker container started with: no network, read-only root filesystem, all
  Linux capabilities dropped, non-root user, memory/CPU/PID limits, a size-
  limited tmpfs and a wall-clock timeout.
* If Docker or the sandbox image is unavailable, execution is REFUSED with a
  clear error. There is no unsafe fallback.
* The host only calls the Docker CLI (``subprocess`` with a list of arguments,
  never ``shell=True``); the experiment code itself never runs in this process.
* Docker is container isolation, not a perfect boundary (containers share the
  host kernel). For stronger isolation use rootless Docker, gVisor (runsc) or
  Firecracker/Kata microVMs. See README.md.

Workflow (human-in-the-loop)::

    executor = CodeExecutor()
    record = executor.submit(code, description="...")   # validate + store
    executor.approve(record.experiment_id, approver="alice")  # a human decides
    result = executor.run(record.experiment_id)         # sandboxed run

Only experiments that were explicitly approved AND whose code file is
byte-identical to the approved version (SHA-256) are executed.

Configuration (environment variables, all optional):
    EXPERIMENT_BASE_DIR (experiments), EXPERIMENT_TIMEOUT_SECONDS (30),
    SANDBOX_IMAGE (scientific-agent-sandbox:latest), SANDBOX_MEMORY (256m),
    SANDBOX_CPUS (1.0), SANDBOX_PIDS (64), MAX_OUTPUT_BYTES (100000).

Run from the project root::

    python -m agents.code_executor
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Dockerfile for the sandbox image. Build with:
#   docker build -t scientific-agent-sandbox:latest -f sandbox/Dockerfile sandbox/
SANDBOX_DOCKERFILE = """\
FROM python:3.11-slim
RUN pip install --no-cache-dir numpy pandas scikit-learn matplotlib scipy \\
    && useradd --uid 65534 --no-create-home --shell /usr/sbin/nologin sandbox || true
WORKDIR /sandbox
USER 65534:65534
"""

EXPERIMENT_ID_PATTERN = re.compile(r"^exp_[0-9a-f]{12}$")

# --- static validation rules (defence in depth only) ----------------------
ALLOWED_IMPORTS = frozenset(
    {
        "numpy", "pandas", "sklearn", "scipy", "matplotlib", "math", "random",
        "statistics", "json", "collections", "itertools", "functools",
        "dataclasses", "typing", "time", "warnings", "datetime",
    }
)
BANNED_CALLS = frozenset(
    {
        "eval", "exec", "compile", "__import__", "open", "input", "breakpoint",
        "globals", "locals", "vars", "getattr", "setattr", "delattr", "exit",
        "quit", "help",
    }
)
BANNED_ATTRIBUTES = frozenset(
    {
        "system", "popen", "spawn", "fork", "execv", "kill", "remove", "unlink",
        "rmdir", "rmtree", "chmod", "chown", "urlopen", "urlretrieve",
    }
)
BANNED_ATTRIBUTE_PREFIXES = ("read_", "fetch_")  # file/network readers
MAX_CODE_BYTES = 100_000


class ExecutionStatus:
    """String constants for ``ExperimentResult.status``."""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED_VALIDATION = "rejected_validation"
    REFUSED_NOT_APPROVED = "refused_not_approved"
    REFUSED_NO_SANDBOX = "refused_no_sandbox"
    REFUSED_TAMPERED = "refused_code_changed_after_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class ExecutorConfig:
    """Executor settings. Use ``ExecutorConfig.from_env()`` for env-based config."""

    base_dir: Path = Path("experiments")
    timeout_seconds: int = 30
    sandbox_image: str = "scientific-agent-sandbox:latest"
    memory_limit: str = "256m"
    cpu_limit: str = "1.0"
    pids_limit: int = 64
    max_output_bytes: int = 100_000
    docker_binary: str = "docker"

    @classmethod
    def from_env(cls) -> "ExecutorConfig":
        """Load configuration from environment variables."""
        return cls(
            base_dir=Path(os.getenv("EXPERIMENT_BASE_DIR", "experiments")),
            timeout_seconds=int(os.getenv("EXPERIMENT_TIMEOUT_SECONDS", "30")),
            sandbox_image=os.getenv("SANDBOX_IMAGE", cls.sandbox_image),
            memory_limit=os.getenv("SANDBOX_MEMORY", cls.memory_limit),
            cpu_limit=os.getenv("SANDBOX_CPUS", cls.cpu_limit),
            pids_limit=int(os.getenv("SANDBOX_PIDS", "64")),
            max_output_bytes=int(os.getenv("MAX_OUTPUT_BYTES", "100000")),
        )

    @property
    def code_dir(self) -> Path:
        return self.base_dir / "generated_code"

    @property
    def results_dir(self) -> Path:
        return self.base_dir / "results"


class ExperimentResult(BaseModel):
    """Structured result for every CodeExecutor operation."""

    experiment_id: str
    status: str
    message: str = ""
    description: str = ""
    validation_issues: List[str] = Field(default_factory=list)
    code_path: Optional[str] = None
    code_sha256: Optional[str] = None
    approved_by: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    execution_time_seconds: Optional[float] = None
    output_dir: Optional[str] = None
    result_path: Optional[str] = None
    finished_at: Optional[str] = None


# --------------------------------------------------------------------------
# Static validation
# --------------------------------------------------------------------------
def validate_code(code: str) -> List[str]:
    """Return a list of problems found in ``code`` (empty list = passed).

    REMINDER: passing validation does NOT make code safe. It is only the first
    filter; the container is the real security boundary.
    """
    issues: List[str] = []
    if not code.strip():
        return ["Code is empty."]
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        return [f"Code exceeds {MAX_CODE_BYTES} bytes."]
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Syntax error on line {exc.lineno}: {exc.msg}"]

    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORTS:
                    issues.append(f"Line {line}: import of '{root}' is not allowed.")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_IMPORTS:
                issues.append(f"Line {line}: import from '{node.module}' is not allowed.")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BANNED_CALLS:
                issues.append(f"Line {line}: call to '{func.id}()' is not allowed.")
        elif isinstance(node, ast.Attribute):
            name = node.attr
            if (
                name.startswith("__")
                or name in BANNED_ATTRIBUTES
                or name.startswith(BANNED_ATTRIBUTE_PREFIXES)
            ):
                issues.append(f"Line {line}: attribute '.{name}' is not allowed.")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            parts = re.split(r"[\\/]", value)
            if value.startswith(("/", "~")) or ".." in parts or "://" in value:
                issues.append(
                    f"Line {line}: absolute paths, '..' and URLs in strings are not "
                    "allowed (write to relative paths only)."
                )
    return issues


# --------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------
class CodeExecutor:
    """Validate, store, approve and sandbox-execute experiment code."""

    def __init__(self, config: Optional[ExecutorConfig] = None) -> None:
        self.config = config or ExecutorConfig.from_env()
        self.config.code_dir.mkdir(parents=True, exist_ok=True)
        self.config.results_dir.mkdir(parents=True, exist_ok=True)

    # -- step 1: submit -----------------------------------------------------
    def submit(self, code: str, description: str = "") -> ExperimentResult:
        """Validate and store code. The experiment is NOT run or approved."""
        issues = validate_code(code)
        experiment_id = f"exp_{uuid.uuid4().hex[:12]}"
        if issues:
            logger.warning("Rejected %s: %d validation issue(s)", experiment_id, len(issues))
            return ExperimentResult(
                experiment_id=experiment_id,
                status=ExecutionStatus.REJECTED_VALIDATION,
                message="Code failed validation and was not stored.",
                description=description,
                validation_issues=issues,
            )
        code_path = self.config.code_dir / f"{experiment_id}.py"
        code_path.write_text(code, encoding="utf-8")
        digest = _sha256_file(code_path)
        self._write_meta(
            experiment_id,
            {"description": description, "sha256": digest, "approved": False,
             "approved_by": None, "approved_sha256": None},
        )
        logger.info("Stored %s (sha256 %s...)", experiment_id, digest[:12])
        return ExperimentResult(
            experiment_id=experiment_id,
            status=ExecutionStatus.PENDING_APPROVAL,
            message="Stored. A human must review the code and call approve().",
            description=description,
            code_path=str(code_path),
            code_sha256=digest,
        )

    # -- step 2: approve ----------------------------------------------------
    def approve(self, experiment_id: str, approver: str) -> ExperimentResult:
        """Record explicit approval for the *current* code file contents."""
        self._check_id(experiment_id)
        if not approver or not approver.strip():
            raise ValueError("approver must identify who reviewed the code")
        meta = self._read_meta(experiment_id)
        code_path = self._code_path(experiment_id)
        digest = _sha256_file(code_path)
        # Re-validate in case the file was edited after submission.
        issues = validate_code(code_path.read_text(encoding="utf-8"))
        if issues:
            return ExperimentResult(
                experiment_id=experiment_id,
                status=ExecutionStatus.REJECTED_VALIDATION,
                message="Stored code no longer passes validation.",
                validation_issues=issues,
            )
        meta.update(approved=True, approved_by=approver.strip(), approved_sha256=digest)
        self._write_meta(experiment_id, meta)
        logger.info("%s approved by %s", experiment_id, approver)
        return ExperimentResult(
            experiment_id=experiment_id,
            status=ExecutionStatus.APPROVED,
            message="Approved for sandboxed execution.",
            description=meta.get("description", ""),
            code_path=str(code_path),
            code_sha256=digest,
            approved_by=approver.strip(),
        )

    # -- step 3: run --------------------------------------------------------
    def run(self, experiment_id: str) -> ExperimentResult:
        """Run an approved experiment inside the sandbox container."""
        self._check_id(experiment_id)
        try:
            meta = self._read_meta(experiment_id)
            code_path = self._code_path(experiment_id)
        except FileNotFoundError as exc:
            return self._finish(ExperimentResult(
                experiment_id=experiment_id, status=ExecutionStatus.ERROR,
                message=f"Experiment not found: {exc}"))

        base = dict(
            experiment_id=experiment_id,
            description=meta.get("description", ""),
            code_path=str(code_path),
            approved_by=meta.get("approved_by"),
        )

        if not meta.get("approved"):
            return self._finish(ExperimentResult(
                **base, status=ExecutionStatus.REFUSED_NOT_APPROVED,
                message="Experiment has not been approved. Call approve() first."))

        digest = _sha256_file(code_path)
        if digest != meta.get("approved_sha256"):
            return self._finish(ExperimentResult(
                **base, status=ExecutionStatus.REFUSED_TAMPERED, code_sha256=digest,
                message="Code changed after approval. Review and approve again."))

        issues = validate_code(code_path.read_text(encoding="utf-8"))
        if issues:
            return self._finish(ExperimentResult(
                **base, status=ExecutionStatus.REJECTED_VALIDATION,
                validation_issues=issues, message="Code failed validation."))

        available, reason = self.sandbox_available()
        if not available:
            logger.error("Refusing to run %s: %s", experiment_id, reason)
            return self._finish(ExperimentResult(
                **base, status=ExecutionStatus.REFUSED_NO_SANDBOX,
                message=f"Secure sandbox unavailable, execution refused. {reason}"))

        out_dir = (self.config.results_dir / experiment_id).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(out_dir, 0o777)  # container user (65534) must write here
        except OSError:  # e.g. Windows; Docker Desktop handles permissions
            pass

        started = time.monotonic()
        try:
            exit_code, stdout, stderr, timed_out = self._run_in_container(
                experiment_id, code_path.resolve(), out_dir)
        except Exception as exc:  # noqa: BLE001 - report any host-side failure
            logger.exception("Sandbox run failed for %s", experiment_id)
            return self._finish(ExperimentResult(
                **base, status=ExecutionStatus.ERROR, code_sha256=digest,
                message=f"Unexpected error starting sandbox: {exc}"))
        elapsed = round(time.monotonic() - started, 3)

        if timed_out:
            status = ExecutionStatus.TIMEOUT
            message = f"Killed after exceeding {self.config.timeout_seconds}s limit."
        elif exit_code == 0:
            status, message = ExecutionStatus.COMPLETED, "Experiment finished."
        else:
            status, message = ExecutionStatus.FAILED, f"Experiment exited with code {exit_code}."

        return self._finish(ExperimentResult(
            **base, status=status, message=message, code_sha256=digest,
            stdout=stdout, stderr=stderr, exit_code=exit_code,
            execution_time_seconds=elapsed, output_dir=str(out_dir)))

    # -- sandbox ------------------------------------------------------------
    def sandbox_available(self) -> Tuple[bool, str]:
        """Check that Docker works and the sandbox image exists."""
        docker = self.config.docker_binary
        if shutil.which(docker) is None:
            return False, (
                "Docker CLI not found. Install Docker and build the sandbox image "
                "(see README.md 'Sandbox setup')."
            )
        try:
            subprocess.run([docker, "info"], capture_output=True, timeout=15, check=True)
            subprocess.run(
                [docker, "image", "inspect", self.config.sandbox_image],
                capture_output=True, timeout=15, check=True)
        except subprocess.CalledProcessError:
            return False, (
                "Docker daemon is not running or image "
                f"'{self.config.sandbox_image}' is missing. Build it with: "
                "docker build -t scientific-agent-sandbox:latest -f sandbox/Dockerfile sandbox/"
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, f"Could not talk to Docker: {exc}"
        return True, "ok"

    def _run_in_container(
        self, experiment_id: str, code_path: Path, out_dir: Path
    ) -> Tuple[Optional[int], str, str, bool]:
        """Run the code in a locked-down container.

        Returns ``(exit_code, stdout, stderr, timed_out)``. Kept separate so it
        can be replaced in unit tests.
        """
        cfg = self.config
        name = f"sci-agent-{experiment_id}"
        cmd = [
            cfg.docker_binary, "run", "--rm", "--name", name,
            "--network", "none",                      # no network access
            "--read-only",                            # read-only root FS
            "--cap-drop", "ALL",                      # no Linux capabilities
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",                  # non-root
            "--pids-limit", str(cfg.pids_limit),      # fork-bomb protection
            "--memory", cfg.memory_limit,
            "--memory-swap", cfg.memory_limit,        # no swap
            "--cpus", cfg.cpu_limit,
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-e", "MPLBACKEND=Agg", "-e", "MPLCONFIGDIR=/tmp", "-e", "HOME=/tmp",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "--mount", f"type=bind,src={code_path},dst=/sandbox/experiment.py,readonly",
            "--mount", f"type=bind,src={out_dir},dst=/sandbox/output",
            "--workdir", "/sandbox/output",
            cfg.sandbox_image, "python", "-I", "/sandbox/experiment.py",
        ]
        logger.info("Starting sandbox container %s", name)
        try:
            proc = subprocess.run(  # list args, no shell
                cmd, capture_output=True, timeout=cfg.timeout_seconds, check=False)
            return (proc.returncode, self._clip(proc.stdout), self._clip(proc.stderr), False)
        except subprocess.TimeoutExpired as exc:
            # Killing the docker CLI is not enough; stop the container itself.
            subprocess.run([cfg.docker_binary, "kill", name],
                           capture_output=True, timeout=15, check=False)
            return (None, self._clip(exc.stdout), self._clip(exc.stderr), True)

    def _clip(self, data: Optional[bytes]) -> str:
        """Decode and truncate captured output."""
        if not data:
            return ""
        text = data[: self.config.max_output_bytes].decode("utf-8", errors="replace")
        if len(data) > self.config.max_output_bytes:
            text += "\n...[output truncated]"
        return text

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _check_id(experiment_id: str) -> None:
        """Reject ids that could escape the experiments directory."""
        if not EXPERIMENT_ID_PATTERN.match(experiment_id):
            raise ValueError(f"Invalid experiment id: {experiment_id!r}")

    def _code_path(self, experiment_id: str) -> Path:
        path = self.config.code_dir / f"{experiment_id}.py"
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return path

    def _meta_path(self, experiment_id: str) -> Path:
        return self.config.code_dir / f"{experiment_id}.meta.json"

    def _read_meta(self, experiment_id: str) -> Dict[str, Any]:
        path = self._meta_path(experiment_id)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_meta(self, experiment_id: str, meta: Dict[str, Any]) -> None:
        self._meta_path(experiment_id).write_text(
            json.dumps(meta, indent=2), encoding="utf-8")

    def _finish(self, result: ExperimentResult) -> ExperimentResult:
        """Stamp and persist a result JSON under experiments/results/."""
        result.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = self.config.results_dir / f"{result.experiment_id}.json"
        try:
            path.write_text(
                json.dumps(result.model_dump(mode="json"), indent=2), encoding="utf-8")
            result.result_path = str(path)
        except OSError as exc:
            logger.error("Could not save result: %s", exc)
        logger.info("%s -> %s", result.experiment_id, result.status)
        return result


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Sample / CLI
# --------------------------------------------------------------------------
SAMPLE_CODE = '''\
import json
import numpy as np
from sklearn.datasets import make_classification
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

X, y = make_classification(n_samples=300, n_features=10, random_state=0)
scores = cross_val_score(LogisticRegression(max_iter=500), X, y, cv=5)
print(json.dumps({"mean_accuracy": float(np.mean(scores))}))
'''


def main() -> None:
    """Demo: submit, (demo-only) self-approve, run. Real use needs human review."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    executor = CodeExecutor()
    record = executor.submit(SAMPLE_CODE, description="sample logistic regression CV")
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    if record.status != ExecutionStatus.PENDING_APPROVAL:
        sys.exit(1)
    # DEMO ONLY: a real deployment must have a human review the code first.
    executor.approve(record.experiment_id, approver="demo-user")
    result = executor.run(record.experiment_id)
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
