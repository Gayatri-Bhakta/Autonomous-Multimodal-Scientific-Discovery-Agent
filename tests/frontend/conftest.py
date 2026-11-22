"""Shared fixtures for frontend tests. All LLM / vision calls are mocked; no API key or network is used."""
import json
import struct
import zlib

import pytest

CHUNKS = [
    {"paper_id": "TEST-A", "title": "Fixture paper A", "url": "https://example.org/a", "year": 2021,
     "text": "Noisy labels reduce the accuracy of graph models by about ten percent on benchmark data."},
    {"paper_id": "TEST-B", "title": "Fixture paper B",
     "text": "Contrastive pretraining improves robustness of encoders when training data is limited."},
    {"paper_id": "TEST-C", "title": "Fixture paper C",
     "text": "Ensembling small models lowers variance across random seeds in low-resource settings."},
]
GOOD_HYPOTHESIS = {
    "title": "Pretraining against label noise",
    "problem_statement": "Graph models lose accuracy under noisy labels.",
    "proposed_solution": "Add contrastive pretraining before supervised training.",
    "cited_paper_ids": ["TEST-A", "TEST-B"],
    "supporting_findings": [
        {"paper_id": "TEST-A", "finding": "Noisy labels reduce the accuracy of graph models"},
        {"paper_id": "TEST-B", "finding": "Contrastive pretraining improves robustness of encoders"}],
    "falsifiable_metric": "Macro-F1 higher than the baseline by at least 2 points over 10 seeds at 20% label noise",
    "expected_code_modules": ["data_loader", "model_training", "evaluation"],
}
CHART_REPLY = {
    "chart_title": "Accuracy vs steps", "chart_type": "line",
    "x_axis": {"label": "Steps", "unit": None}, "y_axis": {"label": "Accuracy", "unit": "%"},
    "baseline_values": [{"label": "Baseline", "value": 71.2, "unit": "%", "reading_type": "observed"}],
    "peak_performance": {"label": "Ours", "value": 84.0, "unit": "%", "reading_type": "estimated"},
    "data_points": [{"series": "Ours", "x": 1000, "y": 80.5, "reading_type": "estimated"},
                    {"series": "Ours", "x": 2000, "y": None}],
    "series": ["Ours"], "trend_summary": "Accuracy rises then plateaus.",
    "evidence": ["Data label 71.2 beside the Baseline line"], "uncertainties": ["Final point unreadable"],
}


def make_png() -> bytes:
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.prompts = reply, error, []

    def complete(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


class FakeVLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error

    def describe(self, system, prompt, image_bytes, mime):
        if self.error:
            raise self.error
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No test may depend on (or leak) real credentials from the developer's environment."""
    for key in ("LLM_PROVIDER", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL", "VLM_PROVIDER", "VLM_API_KEY", "VLM_MODEL",
                "VLM_BASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ENABLE_CODE_EXECUTION"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
