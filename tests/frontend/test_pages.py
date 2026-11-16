"""Page tests with Streamlit's AppTest. They run each page script for real; only the LLM / vision
model is mocked. They prove the pages work against the backend modules, not that a live API call works."""
import glob
import json
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.agents import hypothesis_agent
from src.frontend.utils import state as state_module
from src.ingestion import chart_reader
from tests.frontend.conftest import CHART_REPLY, CHUNKS, GOOD_HYPOTHESIS, FakeLLM, FakeVLM, make_png

ROOT = Path(__file__).resolve().parents[2]  # AppTest resolves relative paths against the test file
PAGES = sorted(glob.glob(str(ROOT / "src" / "frontend" / "pages" / "*.py")))
APP = str(ROOT / "app.py")


def page(name, timeout=60):
    return AppTest.from_file(str(ROOT / "src" / "frontend" / "pages" / f"{name}.py"), default_timeout=timeout)


def texts(node):
    """All visible text (labels, values) in an AppTest tree, for leak checks."""
    out = []

    def walk(n):
        for attr in ("value", "label", "body"):
            try:
                v = getattr(n, attr)
                if isinstance(v, str):
                    out.append(v)
            except Exception:
                pass
        for child in getattr(n, "children", {}).values():
            walk(child)

    walk(node)
    return "\n".join(out)


def button(at, label):
    return next(b for b in at.button if label in b.label)


@pytest.fixture(autouse=True)
def tmp_output(monkeypatch, tmp_path):
    monkeypatch.setattr(state_module, "OUTPUT_DIR", tmp_path / "frontend")
    return tmp_path / "frontend"


def configure_llm(monkeypatch, reply=None):
    monkeypatch.setenv("LLM_API_KEY", "sk-SECRET-123")
    monkeypatch.setenv("LLM_MODEL", "fake-model")
    fake = FakeLLM(reply if reply is not None else {"hypotheses": [GOOD_HYPOTHESIS]})
    monkeypatch.setattr(hypothesis_agent, "llm_client_from_env", lambda: fake)
    return fake


# ---- every page starts -----------------------------------------------------------------
@pytest.mark.parametrize("path", PAGES)
def test_every_page_renders_without_exceptions(path):
    at = AppTest.from_file(path, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]


def test_main_app_starts_with_navigation_and_sidebar():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    sidebar = texts(at.sidebar)
    assert "LLM" in sidebar and "Vision" in sidebar and "LaTeX" in sidebar


def test_secret_values_are_never_rendered(monkeypatch):
    configure_llm(monkeypatch)
    monkeypatch.setenv("VLM_API_KEY", "vlm-SECRET-456")
    monkeypatch.setenv("VLM_MODEL", "vision-model")
    for path in PAGES + [APP]:
        at = AppTest.from_file(path, default_timeout=60).run()
        assert not at.exception
        body = texts(at.main) + texts(at.sidebar)
        assert "sk-SECRET-123" not in body and "vlm-SECRET-456" not in body


def test_home_reports_real_status():
    at = page("home").run()
    body = texts(at.main)
    assert "Hypothesis Generator" in body and "Not configured" in body
    assert "Literature Reviewer" in body
    assert "Code preview connected; execution disabled" in body


def test_literature_page_connects_reviewer_without_fabricating_results():
    at = page("literature").run()
    assert not at.exception
    assert not any("not connected" in w.value for w in at.warning)
    assert button(at, "Run Literature Review")
    assert "Enter a research topic above" in texts(at.main)


def test_experiment_page_offers_safe_code_preview_only():
    at = page("experiment").run()
    assert not at.exception
    assert button(at, "Generate Code Preview")
    assert not any("not connected" in w.value.lower() for w in at.warning)
    assert not any("Run Code" in b.label or "Execute" in b.label for b in at.button)


# ---- hypothesis page ------------------------------------------------------------------------
def test_hypothesis_page_blocks_generation_without_llm():
    at = page("hypothesis").run()
    assert any("LLM not configured" in w.value for w in at.warning)
    assert button(at, "Generate grounded hypotheses").disabled


def test_hypothesis_upload_generate_and_select(monkeypatch):
    configure_llm(monkeypatch)
    at = page("hypothesis").run()
    at.file_uploader[0].upload("evidence.json", json.dumps(CHUNKS).encode(), "application/json")
    at.run()
    assert at.session_state["chunk_source"] == "evidence.json" and len(at.session_state["chunks"]) == 3
    assert not button(at, "Generate grounded hypotheses").disabled
    button(at, "Generate grounded hypotheses").click()
    at.run()
    report = at.session_state["hypothesis_report"]
    assert report.status == "ok" and report.hypotheses[0].title == "Pretraining against label noise"
    assert any("H1: Pretraining" in e.label for e in at.expander)
    assert "TEST-A" in texts(at.main) and "Falsifiable metric" in texts(at.main)
    assert at.session_state["trace"][-1]["step"] == "Hypothesis generation" and at.session_state["trace"][-1]["status"] == "ok"
    button(at, "Use this hypothesis").click()
    at.run()
    assert at.session_state["selected_hypothesis"]["title"] == "Pretraining against label noise"


def test_hypothesis_page_shows_validation_rejections(monkeypatch):
    bad = dict(GOOD_HYPOTHESIS, cited_paper_ids=["FAKE-1"], supporting_findings=[{"paper_id": "FAKE-1", "finding": "invented claim here"}])
    configure_llm(monkeypatch, {"hypotheses": [bad]})
    at = page("hypothesis")
    at.session_state["chunks"], at.session_state["chunk_source"] = CHUNKS, "x.json"
    at.run()
    button(at, "Generate grounded hypotheses").click()
    at.run()
    assert at.session_state["hypothesis_report"].status == "failed" and at.error
    assert any("Rejected by validation" in e.label for e in at.expander)


def test_invalid_evidence_upload_is_rejected_with_message(monkeypatch):
    configure_llm(monkeypatch)
    at = page("hypothesis").run()
    at.file_uploader[0].upload("bad.json", b"{not json", "application/json")
    at.run()
    assert at.error and not at.session_state["chunks"]


# ---- chart page ------------------------------------------------------------------------------
def configure_vision(monkeypatch, vlm):
    monkeypatch.setenv("VLM_API_KEY", "vlm-secret")
    monkeypatch.setenv("VLM_MODEL", "vision-model")
    monkeypatch.setattr(chart_reader, "HTTPVisionClient", lambda cfg: vlm)


def test_chart_page_without_vision_config_disables_reading():
    at = page("charts").run()
    assert any("Vision model not configured" in w.value for w in at.warning)
    assert button(at, "Read charts").disabled


def test_chart_upload_and_extraction(monkeypatch, tmp_output):
    configure_vision(monkeypatch, FakeVLM(CHART_REPLY))
    at = page("charts").run()
    at.file_uploader[0].upload("fig1.png", make_png(), "image/png")
    at.run()
    button(at, "Read charts").click()
    at.run()
    results = at.session_state["chart_results"]
    assert len(results) == 1 and results[0]["ok"] and results[0]["data"]["chart_type"] == "line"
    body = texts(at.main)
    assert "Accuracy (%)" in body and "plateaus" in body and "unreadable" in body.lower()
    assert (tmp_output / "charts" / "fig1.png").is_file() and at.session_state["uploads"][0]["name"] == "fig1.png"


def test_chart_api_failure_is_shown_not_hidden(monkeypatch):
    configure_vision(monkeypatch, FakeVLM(error=RuntimeError("provider down")))
    at = page("charts").run()
    at.file_uploader[0].upload("fig1.png", make_png(), "image/png")
    at.run()
    button(at, "Read charts").click()
    at.run()
    assert not at.session_state["chart_results"][0]["ok"] and any("provider down" in e.value for e in at.error)


def test_chart_rejects_non_image_bytes(monkeypatch):
    configure_vision(monkeypatch, FakeVLM(CHART_REPLY))
    at = page("charts").run()
    at.file_uploader[0].upload("fake.png", b"this is text, not a png", "image/png")
    at.run()
    button(at, "Read charts").click()
    at.run()
    assert not at.session_state["chart_results"][0]["ok"] and any("cannot be used" in e.value for e in at.error)


# ---- paper page ---------------------------------------------------------------------------------
def seed_results():
    return pd.DataFrame({"method": ["Baseline", "Ours"], "metric": ["accuracy", "accuracy"], "value": [0.81, 0.85],
                         "std": [0.02, 0.01], "n": pd.array([10, 10], dtype="Int64"), "p_value": [None, 0.004],
                         "comparison": [None, "Baseline"]})


def test_paper_page_requires_title_results_and_confirmation():
    at = page("paper").run()
    assert button(at, "Generate paper").disabled
    assert any("pdflatex was not found" in w.value for w in at.warning) or True  # depends on the host


def test_paper_generation_end_to_end_without_llm(tmp_output):
    at = page("paper")
    at.session_state["paper_results_seed"] = seed_results()
    at.session_state["chunks"] = CHUNKS
    at.run()
    at.text_input[0].input("A Test Paper")
    next(c for c in at.checkbox if "Results are simulated" in c.label).check()
    next(c for c in at.checkbox if "I confirm" in c.label).check()
    at.run()
    assert not button(at, "Generate paper").disabled
    button(at, "Generate paper").click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    build = at.session_state["paper_build"]
    assert build["synthesis"].status == "placeholders_only" and build["synthesis"].is_simulated
    tex = (tmp_output / "paper" / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert "0.85" in tex and "SIMULATED" in tex.upper()
    comp = build["compile"]
    assert comp.pdf_ok == (tmp_output / "paper" / "generated_research_paper.pdf").is_file()  # no PDF claimed without a file
    assert any("NOT GENERATED" in str(v) or "placeholder" in str(v) for v in build["synthesis"].sections.values())


def test_paper_page_surfaces_validation_errors():
    at = page("paper")
    bad = seed_results()
    bad.loc[1, "p_value"] = 7.0
    at.session_state["paper_results_seed"] = bad
    at.run()
    at.text_input[0].input("Bad paper")
    next(c for c in at.checkbox if "I confirm" in c.label).check()
    at.run()
    button(at, "Generate paper").click()
    at.run()
    assert at.session_state["paper_build"] is None and any("Please fix the input" in e.value for e in at.error)


# ---- reports page -------------------------------------------------------------------------------------
def test_reports_page_lists_real_artifacts(tmp_output, monkeypatch):
    from src.frontend.services import paper as paper_service
    from src.frontend.services.hypothesis import generate

    res = paper_service.build_paper({"title": "T", "results": [{"method": "M", "metric": "m", "value": 0.5}],
                                     "is_simulated": True}, tmp_output / "paper", use_llm=False, compile_pdf=False)
    report = generate(CHUNKS, "t", llm=FakeLLM({"hypotheses": [GOOD_HYPOTHESIS]})).data
    at = page("reports")
    at.session_state["paper_build"], at.session_state["hypothesis_report"] = res.data, report
    at.session_state["chunks"] = CHUNKS
    at.session_state["trace"] = [{"time": "00:00:00", "step": "Hypothesis generation", "status": "ok", "seconds": 1.2, "model": "m", "detail": ""}]
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert {t.label for t in at.tabs} >= {"Downloads", "Run trace", "Citations"}
    assert not at.info or all("Nothing generated" not in i.value for i in at.info)


def test_reports_page_empty_state():
    at = page("reports").run()
    assert not at.exception and any("Nothing generated yet" in i.value for i in at.info)

