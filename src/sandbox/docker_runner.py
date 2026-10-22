from typing import Any

from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import ReadTimeout
import docker
from docker.errors import DockerException


IMAGE_NAME = "scientific-sandbox:latest"


def execute_code_in_sandbox(
    code_string: str,
    timeout_sec: int = 30,
) -> dict[str, Any]:
    """Run Python code in an isolated Docker container."""
    client = docker.from_env()
    container = None

    try:
        container = client.containers.run(
            image=IMAGE_NAME,
            command=["python", "-c", code_string],
            detach=True,
            network_mode="none",
            mem_limit="1g",
            cpu_quota=100_000,
            cpu_period=100_000,
            user="sandboxuser",
        )

        try:
            result = container.wait(timeout=timeout_sec)
            timed_out = False
            exit_code = result.get("StatusCode", 1)
        except (ReadTimeout, RequestConnectionError):
            timed_out = True
            exit_code = -1

        if timed_out:
            container.kill()
            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )
        else:
            stdout = container.logs(stdout=True, stderr=False).decode(
                "utf-8", errors="replace"
            )
            stderr = container.logs(stdout=False, stderr=True).decode(
                "utf-8", errors="replace"
            )

        return {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
        }

    except DockerException as exc:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Docker error: {exc}",
            "timed_out": False,
        }
    finally:
        if container is not None:
            container.remove(force=True)
        client.close()