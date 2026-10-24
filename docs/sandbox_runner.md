# Containerized Docker Execution Sandbox (Member 4, Week 2)

`src/sandbox/docker_runner.py` executes LLM-generated Python experiment scripts inside an isolated Docker container with strict resource limits and security constraints.

---

## 1. Security Architecture & Resource Bounds

| Constraint | Configuration | Purpose |
| :--- | :--- | :--- |
| **Network Isolation** | `network_mode="none"` | Eliminates network egress and ingress; prevents SSRF and data exfiltration. |
| **Memory Ceiling** | `mem_limit="1g"` | Prevents host exhaustion or Out-Of-Memory (OOM) Denial of Service. |
| **CPU Quota** | `cpu_quota=100_000`, `cpu_period=100_000` | Caps execution to exactly 1 CPU core on the host system. |
| **Privilege Dropping**| `user="sandboxuser"` | Executes as an unprivileged non-root user inside the container. |
| **Execution Timeout** | `timeout_sec=30` (default) | Terminates runaway loops (`container.kill()`) and returns `timed_out=True`. |
| **Lifecycle Cleanup** | `finally: container.remove(force=True)` | Ensures no dangling or zombie containers remain after execution. |

---

## 2. Sandbox Container Specification (`sandbox/Dockerfile`)

```dockerfile
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir numpy pandas scipy scikit-learn matplotlib

RUN groupadd --system sandboxuser && useradd --system --gid sandboxuser --create-home sandboxuser

WORKDIR /workspace
USER sandboxuser
```

* Base image: `python:3.10-slim`
* Pre-installed scientific packages: `numpy`, `pandas`, `scipy`, `scikit-learn`, `matplotlib`
* Non-root user: `sandboxuser` in group `sandboxuser`
* Execution directory: `/workspace`

---

## 3. Python API & Usage

```python
from src.sandbox.docker_runner import execute_code_in_sandbox, is_docker_available

# Check daemon availability
if is_docker_available():
    result = execute_code_in_sandbox(
        code_string="import numpy as np; print('Mean:', np.mean([1, 2, 3]))",
        timeout_sec=15
    )
    print(result)
```

### Return Schema (`dict[str, Any]`):
```python
{
    "exit_code": int,      # 0 on success, non-zero on error, -1 on timeout or Docker exception
    "stdout": str,         # Decoded standard output
    "stderr": str,         # Decoded standard error (or Docker exception details)
    "timed_out": bool      # True if the script exceeded timeout_sec and was killed
}
```

---

## 4. Building the Sandbox Image

Before executing code in Docker, build the container image once:

```bash
docker build -t scientific-sandbox:latest -f sandbox/Dockerfile .
```

---

## 5. Automated Tests

```bash
pytest tests/test_sandbox_security.py -v
```

The test suite covers:
1. **Security Isolation & Resource Allocation (Unit / Mock):** Verifies `network_mode="none"`, `mem_limit="1g"`, CPU quotas, and `user="sandboxuser"` parameters passed to Docker SDK.
2. **Timeout Enforcement:** Verifies timeout detection and container termination via `container.kill()`.
3. **Daemon Resilience:** Verifies graceful error dictionary return on `DockerException` without uncaught crashes.
4. **Dockerfile Specification:** Asserts standard library and security boundaries in `sandbox/Dockerfile`.
5. **Live Integration Tests:** Automatically executed when the Docker daemon is online, skipped safely when offline.
