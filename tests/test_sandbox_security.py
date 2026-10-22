from src.sandbox.docker_runner import execute_code_in_sandbox


def test_sandbox_blocks_network():
    code = """
import urllib.request

try:
    urllib.request.urlopen("https://example.com", timeout=3)
except Exception:
    print("NETWORK_BLOCKED")
else:
    print("NETWORK_ALLOWED")
"""

    result = execute_code_in_sandbox(code)

    assert result["timed_out"] is False
    assert "NETWORK_BLOCKED" in result["stdout"]
    assert "NETWORK_ALLOWED" not in result["stdout"]


def test_sandbox_stops_code_after_timeout():
    result = execute_code_in_sandbox(
        "import time; time.sleep(5)",
        timeout_sec=2,
    )

    assert result["timed_out"] is True
    assert result["exit_code"] == -1