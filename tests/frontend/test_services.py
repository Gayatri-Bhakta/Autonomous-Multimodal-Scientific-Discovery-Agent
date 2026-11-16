"""Service-layer tests: the adapters between the Streamlit pages and the real backend modules."""
import json

import pytest

from src.frontend.services import charts, hypothesis, paper
from src.frontend.services.status import environment_status, module_status
from src.frontend.utils import env as env_utils
from src.frontend.utils.files import make_zip, safe_filename, validate_upload
from tests.frontend.conftest import CHART_REPLY, CHUNKS, GOOD_HYPOTHESIS, FakeLLM, FakeVLM, make_png

CHUNK_BYTES = json.dumps(CHUNKS).encode()


# ---- evidence upload ------------------------------------------------------------------------
def test_parse_chunks_json_and_jsonl():
    assert hypothesis.parse_chunks(CHUNK_BYTES, "e.json").ok
    jsonl = "\n".join(json.dumps(c) for c in CHUNKS).encode()
    res = hypothesis.parse_chunks(jsonl, "e.jsonl")
    assert res.ok and len(res.data) == 3


@pytest.mark.parametrize("data,name,code", [(b"not json", "e.json", "invalid_upload"), (b"[]", "e.json", "invalid_upload"),
                                            (b'{"a": 1}', "e.json", "invalid_upload"), (CHUNK_BYTES, "e.txt", "invalid_upload"),
                                            (b'[{"title": "no id or text"}]', "e.json", "invalid_upload")])
def test_parse_chunks_rejects_bad_files(data, name, code):
    res = hypothesis.parse_chunks(data, name)
    assert not res.ok and res.code == code and res.message


def test_summarize_chunks_merges_same_paper():
    rows = hypothesis.summarize_chunks(CHUNKS + [{"paper_id": "TEST-A", "text": "More text from paper A."}])
    assert len(rows) == 3 and next(r for r in rows if r["paper_id"] == "TEST-A")["chunks"] == 2


# ---- hypothesis generation (mocked LLM) ----------------------------------------------------------
def test_generate_valid_hypotheses():
    res = hypothesis.generate(CHUNKS, "label noise", 3, True, llm=FakeLLM({"hypotheses": [GOOD_HYPOTHESIS]}))
    assert res.ok and res.code == "ok" and res.data.hypotheses[0].cited_paper_ids == ["TEST-A", "TEST-B"]


def test_generate_without_llm_is_a_clear_failure_not_fake_output():
    res = hypothesis.generate(CHUNKS, "x")
    assert not res.ok and "No LLM configured" in res.message and res.data.hypotheses == []


def test_generate_reports_insufficient_evidence_partial_and_llm_errors():
    one = hypothesis.generate(CHUNKS[:1], "x", llm=FakeLLM({"hypotheses": [GOOD_HYPOTHESIS]}))
    assert not one.ok and one.code == "insufficient_evidence"
    bad = dict(GOOD_HYPOTHESIS, cited_paper_ids=["NOPE"], supporting_findings=[{"paper_id": "NOPE", "finding": "invented claim text"}])
    part = hypothesis.generate(CHUNKS, "x", llm=FakeLLM({"hypotheses": [GOOD_HYPOTHESIS, bad]}))
    assert part.ok and part.code == "partial" and len(part.data.rejected) == 1
    assert not hypothesis.generate(CHUNKS, "x", llm=FakeLLM(error=RuntimeError("boom"))).ok
    assert not hypothesis.generate(CHUNKS, "x", llm=FakeLLM("garbage")).ok


# ---- chart reader (mocked vision model) ------------------------------------------------------------------
def test_read_chart_success_and_helpers():
    res = charts.read_chart(make_png(), "fig 1.png", client=FakeVLM(CHART_REPLY))
    assert res.ok and res.data["chart_type"] == "line"
    df = charts.points_dataframe(res.data)
    assert len(df) == 1 and df.iloc[0]["y"] == 80.5  # the unreadable (None) point is not plotted
    text = charts.explanation(res.data)
    assert "line" in text and "Accuracy (%)" in text and "plateaus" in text and "unreadable" in text


@pytest.mark.parametrize("data,name,client,code", [
    (b"definitely not an image", "a.png", FakeVLM(CHART_REPLY), "invalid_image"),
    (make_png(), "a.bmp", FakeVLM(CHART_REPLY), "invalid_image"),
    (make_png(), "a.png", FakeVLM("not json"), "invalid_response"),
    (make_png(), "a.png", FakeVLM(error=RuntimeError("down")), "api_error"),
])
def test_read_chart_errors_are_friendly(data, name, client, code):
    res = charts.read_chart(data, name, client=client)
    assert not res.ok and res.code == code and res.message


def test_read_chart_without_vision_config():
    res = charts.read_chart(make_png(), "a.png")
    assert not res.ok and res.code == "config" and "not configured" in res.message


# ---- paper ------------------------------------------------------------------------------------------------------
def test_parse_helpers_and_references_from_chunks():
    assert paper.parse_authors("Ada L | MIT\n\nBob") == [{"name": "Ada L", "affiliation": "MIT"}, {"name": "Bob", "affiliation": None}]
    assert paper.parse_lines(" a \n\n b ") == ["a", "b"]
    metas = paper.metas_from_chunks(CHUNKS, ["TEST-A", "TEST-C"])
    assert [m["paper_id"] for m in metas] == ["TEST-A", "TEST-C"] and metas[0]["url"] == "https://example.org/a"


def paper_data(**kw):
    data = {"title": "A Test Paper", "authors": [{"name": "A. Author", "affiliation": None}], "hypothesis": "H",
            "experimental_setup": "Setup facts.", "results": [{"method": "M1", "metric": "acc", "value": 0.8, "std": 0.01, "n": 5}],
            "figures": [], "papers": paper.metas_from_chunks(CHUNKS), "limitations": [], "is_simulated": True}
    data.update(kw)
    return data


def test_build_paper_placeholder_only_without_pdf(tmp_path):
    res = paper.build_paper(paper_data(), tmp_path, use_llm=False, compile_pdf=False)
    assert res.ok and res.data["compile"] is None and res.data["synthesis"].status == "placeholders_only"
    assert (tmp_path / "generated_research_paper.tex").is_file() and (tmp_path / "references.bib").is_file()


def test_build_paper_never_claims_a_pdf_that_does_not_exist(tmp_path):
    res = paper.build_paper(paper_data(), tmp_path, use_llm=False, compile_pdf=True)
    comp = res.data["compile"]
    assert res.ok
    if comp.pdf_ok:
        assert (tmp_path / "generated_research_paper.pdf").is_file()
    else:
        assert comp.pdf_path is None and comp.fallback_files


def test_build_paper_errors(tmp_path):
    assert paper.build_paper(paper_data(), tmp_path, use_llm=True).code == "config"  # no LLM configured
    bad = paper.build_paper(paper_data(title=""), tmp_path, use_llm=False)
    assert not bad.ok and bad.code == "invalid_input"
    nan = paper.build_paper(paper_data(results=[{"method": "M", "metric": "m", "value": 0.5, "p_value": 7}]), tmp_path, use_llm=False)
    assert not nan.ok and nan.code == "invalid_input"


# ---- status, secrets, files --------------------------------------------------------------------------------------
def test_status_never_contains_secret_values(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-SECRET-123")
    monkeypatch.setenv("LLM_MODEL", "some-model")
    dump = json.dumps({"env": environment_status(), "modules": module_status()}, default=str)
    assert "sk-SECRET-123" not in dump and "some-model" in dump


def test_module_status_states():
    rows = {r["week"]: r for r in module_status()}
    assert rows["Week 4"]["state"] == "ready" and rows["Week 2"]["state"] == "needs_config"
    assert rows["Week 1"]["state"] == "ready"
    assert rows["Executor"]["state"] == "ready"  # preview adapter connected; execution remains disabled
    assert "execution disabled" in rows["Executor"]["detail"].lower()


def test_env_status_and_flags(monkeypatch):
    assert not env_utils.llm_status()["configured"] and not env_utils.code_execution_enabled()
    monkeypatch.setenv("LLM_API_KEY", "k")
    assert not env_utils.llm_status()["configured"]  # model also required
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("ENABLE_CODE_EXECUTION", "true")
    assert env_utils.llm_status()["configured"] and env_utils.code_execution_enabled()


def test_validate_upload_and_filenames():
    assert validate_upload("a.png", b"x", (".png",), 1) is None
    assert "unsupported" in validate_upload("a.exe", b"x", (".png",), 1)
    assert "empty" in validate_upload("a.png", b"", (".png",), 1)
    assert "limit" in validate_upload("a.png", b"x" * 2_000_000, (".png",), 1)
    assert safe_filename("../../etc/passwd") == "passwd" and safe_filename("my chart (1).png") == "my_chart_1_.png"
    assert safe_filename("") == "upload"


def test_make_zip_roundtrip():
    import io
    import zipfile

    data = make_zip({"a/b.txt": b"hello", "c.json": b"{}"})
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert sorted(z.namelist()) == ["a/b.txt", "c.json"] and z.read("a/b.txt") == b"hello"

