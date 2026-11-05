"""Tests for SynthesizerAgent. The LLM is always mocked: no API key or network is needed.
Passing these tests does NOT prove that a real LLM produces acceptable text."""
import copy
import json
import re
import shutil

import pytest

from src.agents.hypothesis_agent import LLMError
from src.agents.synthesizer_agent import (
    InputValidationError, PaperInput, PaperMeta, SynthesizerAgent, SynthesizerConfigError, TemplateError,
    _Context, build_allowed_numbers, build_bibtex, build_results_table, check_and_render, extract_numbers,
    find_unverified_numbers, latex_escape, load_template, render_template, validate_paper_input,
)
from src.utils.latex_compiler import compile_pdf

def _make_png() -> bytes:
    """A valid 1x1 PNG (correct CRCs, so pdflatex can really include it)."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


PNG = _make_png()

DATA = {
    "title": "Model B versus a Baseline",
    "authors": [{"name": "A. Author", "affiliation": "Example Lab"}, "B. Author"],
    "hypothesis": "Model B improves accuracy over the baseline.",
    "experimental_setup": "Both models are trained on a synthetic dataset with 10 seeds.",
    "results": [
        {"method": "Baseline", "metric": "accuracy", "value": 0.80, "std": 0.02, "n": 10},
        {"method": "Model B", "metric": "accuracy", "value": 0.85, "std": 0.01, "n": 10, "p_value": 0.004,
         "comparison": "Baseline"},
    ],
    "limitations": ["Synthetic data only."],
    "papers": [
        {"paper_id": "arxiv:1706.03762", "title": "Attention Is All You Need", "year": 2017,
         "authors": ["Ashish Vaswani", "Noam Shazeer"], "url": "https://arxiv.org/abs/1706.03762"},
        {"paper_id": "arxiv:1412.6980", "title": "Adam: A Method for Stochastic Optimization", "year": 2014,
         "authors": ["Diederik P. Kingma", "Jimmy Ba"]},
    ],
}
ANSWERS = {
    "abstract": "Model B reaches 0.85 accuracy compared with 0.8 for the baseline, as shown in \\ref{tab:results}.",
    "introduction": "Attention models are widely studied \\cite{vaswani2017attention}. Optimisation matters too "
                    "\\cite{kingma2014adam}. This study tests the stated hypothesis on a simple task.",
    "experimental_setup": "Both models are trained on a synthetic dataset using 10 random seeds and compared directly.",
    "results_discussion": "See \\ref{tab:results}: Model B scores 0.85 while the baseline scores 0.80, with p=0.004 "
                          "reported for the comparison.",
    "conclusion": "Model B scored higher than the baseline in this experiment. Only synthetic data were used, so "
                  "the finding is limited.",
}


class FakeLLM:
    """Answers by section. ``script[section]`` may be a list of answers/exceptions used in order."""

    def __init__(self, answers=None, script=None, error=None):
        self.answers, self.script, self.error = dict(ANSWERS, **(answers or {})), script or {}, error
        self.prompts, self.calls = [], {}

    def complete(self, prompt):
        section = re.search(r"SECTION: (\w+)", prompt).group(1)
        self.prompts.append(prompt)
        self.calls[section] = self.calls.get(section, 0) + 1
        if self.error:
            raise self.error
        if section in self.script:
            item = self.script[section].pop(0) if self.script[section] else self.answers[section]
            if isinstance(item, Exception):
                raise item
            return item
        return self.answers[section]


def run(tmp_path, data=None, llm=None, **kw):
    agent = SynthesizerAgent(llm=llm or FakeLLM(), use_env_llm=False, **kw.pop("agent_kw", {}))
    result = agent.synthesize(data or DATA, output_dir=tmp_path / "out", **kw)
    return result, agent, (tmp_path / "out")


# ---- template loading -------------------------------------------------------------
def test_default_template_loads_with_all_placeholders():
    text = load_template()
    for name in ("TITLE", "AUTHORS", "ABSTRACT", "INTRODUCTION", "EXPERIMENTAL_SETUP", "RESULTS_TABLE",
                 "FIGURES", "CONCLUSION", "BIBLIOGRAPHY"):
        assert f"<<{name}>>" in text
    assert r"\documentclass" in text and r"\end{document}" in text


def test_missing_template_and_missing_placeholder(tmp_path):
    with pytest.raises(TemplateError, match="not found"):
        load_template(tmp_path / "nope.tex")
    bad = tmp_path / "bad.tex"
    bad.write_text(load_template().replace("<<CONCLUSION>>", ""), encoding="utf-8")
    with pytest.raises(TemplateError, match="CONCLUSION"):
        load_template(bad)
    with pytest.raises(TemplateError):
        SynthesizerAgent(llm=FakeLLM(), template_path=bad, use_env_llm=False).synthesize(DATA, tmp_path / "o")


def test_placeholders_in_comments_are_ignored():
    tpl = "% mentions <<TITLE>> here\n" + load_template()
    path_text = "\n".join(l for l in tpl.splitlines() if not l.lstrip().startswith("%"))
    assert "% mentions" not in path_text


def test_render_is_single_pass_and_detects_unknown_placeholders():
    out = render_template("<<A>> and <<B>>", {"A": "<<B>>", "B": "x"})
    assert out == "<<B>> and x"  # inserted text is not re-scanned
    with pytest.raises(TemplateError):
        render_template("<<A>> <<Z>>", {"A": "1"})


# ---- input validation --------------------------------------------------------------
def test_valid_minimal_and_alias_inputs():
    paper = validate_paper_input({"title": "T", "hypothesis": "H"})
    assert paper.results == [] and paper.authors == []
    full = validate_paper_input({**DATA, "experimental_setup": {"dataset": "synthetic", "seeds": 10}})
    assert full.authors[1].name == "B. Author" and "dataset: synthetic" in full.experimental_setup
    meta = PaperMeta.model_validate({"arxiv_id": "2401.00001", "title": "X", "published": "2024-01-15", "journal": "J"})
    assert (meta.paper_id, meta.year, meta.venue) == ("arxiv:2401.00001", 2024, "J")
    assert PaperMeta.model_validate({"pmid": "99", "title": "Y"}).paper_id == "pubmed:99"
    assert isinstance(validate_paper_input(full), PaperInput)


@pytest.mark.parametrize("change,fragment", [
    ({"title": ""}, "title"), ({"title": "   "}, "title"),
    ({"results": [], "hypothesis": None}, "nothing to write about"),
    ({"results": [{"method": "M", "metric": "x", "value": float("nan")}]}, "finite"),
    ({"results": [{"method": "M", "metric": "x", "value": 1, "p_value": 1.7}]}, "between 0 and 1"),
    ({"results": [{"method": "M", "metric": "x", "value": 1, "p_value": -0.1}]}, "between 0 and 1"),
    ({"results": [{"method": "M", "metric": "x", "value": 1, "std": -1}]}, "std"),
    ({"results": [{"method": "M", "metric": "x", "value": 1, "n": 0}]}, "n must be"),
    ({"results": [{"method": " ", "metric": "x", "value": 1}]}, "blank"),
    ({"results": [{"method": "M", "metric": "x", "value": "abc"}]}, "value"),
    ({"figures": [{"path": "/no/such/figure.png"}]}, "not found"),
    ({"figures": [{"path": "figure.gif"}]}, "must be a .png"),
    ({"authors": [{"name": " "}]}, "blank"),
    ({"papers": [{"title": "no id"}]}, "paper_id"),
    ({"papers": [{"paper_id": "p", "year": 5}]}, "year"),
])
def test_invalid_inputs_are_rejected_with_clear_messages(change, fragment):
    data = {**copy.deepcopy(DATA), **change}
    with pytest.raises(InputValidationError) as err:
        validate_paper_input(data)
    assert fragment in str(err.value) and err.value.problems


def test_all_problems_reported_together_and_bad_types():
    with pytest.raises(InputValidationError) as err:
        validate_paper_input({"title": "", "results": [{"method": "M", "metric": "x", "value": 1, "p_value": 3}]})
    assert len(err.value.problems) >= 2
    for bad in (None, "text", 5, ["x"]):
        with pytest.raises(InputValidationError):
            validate_paper_input(bad)


def test_duplicate_figure_labels_rejected(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(PNG)
    with pytest.raises(InputValidationError, match="unique"):
        validate_paper_input({**DATA, "figures": [{"path": str(img), "label": "x"}, {"path": str(img), "label": "x"}]})


def test_synthesize_validates_before_calling_the_llm(tmp_path):
    llm = FakeLLM()
    with pytest.raises(InputValidationError):
        SynthesizerAgent(llm=llm, use_env_llm=False).synthesize({"title": ""}, tmp_path)
    assert llm.prompts == [] and not list(tmp_path.iterdir())


# ---- successful synthesis ----------------------------------------------------------------
def test_synthesis_writes_tex_and_bib_with_verified_numbers(tmp_path):
    result, _, out = run(tmp_path)
    assert result.status == "complete" and set(result.sections.values()) == {"llm"}
    tex = (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert "<<" not in tex and r"\begin{abstract}" in tex and r"\label{tab:results}" in tex
    assert "0.8" in tex and "0.85" in tex and "$0.004$" in tex  # p-value comes from the data via code, not the LLM
    assert "Table~\\ref{tab:results}" in tex
    assert "\\cite{vaswani2017attention}" in tex and "\\bibliography{references}" in tex
    assert set(result.cited_keys) == {"vaswani2017attention", "kingma2014adam"}
    assert (out / "references.bib").read_text(encoding="utf-8").count("@misc") == 2
    assert result.tex_path.endswith("generated_research_paper.tex")


def test_table_is_built_by_code_from_the_data(tmp_path):
    table = build_results_table(PaperInput.model_validate(DATA).results)
    assert "Baseline & accuracy & 0.8 & 0.02 & 10" in table
    assert "Model B & accuracy & 0.85 & 0.01 & 10 & $0.004$ & Baseline" in table
    assert "$p$" in table and "vs." in table
    assert build_results_table([]) .startswith(r"\textbf{[RESULTS NOT PROVIDED")
    tiny = PaperInput.model_validate({**DATA, "results": [{"method": "M", "metric": "x", "value": 1, "p_value": 0.0001}]})
    assert "$<0.001$" in build_results_table(tiny.results)


def test_every_prompt_contains_rules_and_only_supplied_facts(tmp_path):
    llm = FakeLLM()
    run(tmp_path, llm=llm)
    prompt = llm.prompts[0]
    assert "Never invent" in prompt and "vaswani2017attention" in prompt and "tab:results" in prompt
    assert "Model B | accuracy = 0.85" in prompt and "SIMULATED" not in prompt
    assert len(llm.prompts) == 5


def test_simulated_flag_is_visible_everywhere(tmp_path):
    llm = FakeLLM()
    _, _, out = run(tmp_path, data={**DATA, "is_simulated": True}, llm=llm)
    tex = (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert "SIMULATED SAMPLE DATA" in tex and "SIMULATED SAMPLE DATA" in llm.prompts[0]


def test_figures_are_copied_and_referenced(tmp_path):
    img = tmp_path / "my chart (1).png"
    img.write_bytes(PNG)
    data = {**DATA, "figures": [{"path": str(img), "caption": "Accuracy & loss", "label": "acc"}]}
    llm = FakeLLM({"results_discussion": "See \\ref{tab:results} and \\ref{fig:acc} for the accuracy results."})
    result, _, out = run(tmp_path, data=data, llm=llm)
    tex = (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert result.figures == ["figures/fig1_my_chart__1_.png"] and (out / result.figures[0]).is_file()
    assert "\\includegraphics[width=\\columnwidth]{figures/fig1_my_chart__1_.png}" in tex
    assert "Accuracy \\& loss" in tex and "\\label{fig:acc}" in tex and "Figure~\\ref{fig:acc}" in tex


# ---- BibTeX -----------------------------------------------------------------------------------
def test_bibtex_entries_and_keys():
    bib = build_bibtex([PaperMeta(**p) for p in DATA["papers"]])
    assert list(bib.keys.values()) == ["vaswani2017attention", "kingma2014adam"]
    assert "@misc{vaswani2017attention," in bib.text and "eprint = {1706.03762}" in bib.text
    assert "archivePrefix = {arXiv}" in bib.text and "title = {{Attention Is All You Need}}" in bib.text
    assert "author = {Ashish Vaswani and Noam Shazeer}" in bib.text


def test_bibtex_never_invents_missing_fields():
    bib = build_bibtex([PaperMeta(paper_id="x:1", title="Only A Title")])
    assert "[AUTHORS MISSING]" in bib.text and "year = {n.d.}" in bib.text and "doi" not in bib.text
    assert any("no authors" in w for w in bib.warnings) and any("no year" in w for w in bib.warnings)


def test_bibtex_skips_untitled_and_duplicate_papers_with_warnings():
    bib = build_bibtex([PaperMeta(paper_id="a", title=""), PaperMeta(paper_id="b", title="T", authors=["X Y"], year=2020),
                        PaperMeta(paper_id="b", title="T again")])
    assert list(bib.keys) == ["b"] and bib.text.count("@misc") == 1
    assert any("no title" in w for w in bib.warnings) and any("duplicate" in w for w in bib.warnings)


def test_bibtex_unique_keys_escaping_and_types():
    papers = [PaperMeta(paper_id="a", title="Same Title", authors=["Ann Lee"], year=2020),
              PaperMeta(paper_id="b", title="Same Title", authors=["Bo Lee"], year=2020),
              PaperMeta(paper_id="pubmed:7", title="R&D_{x} 50% {gain}", authors=["Lee, Ann"], year=2021,
                        venue="J. Tests", doi="10.1/x")]
    bib = build_bibtex(papers)
    assert len(set(bib.keys.values())) == 3 and bib.keys["a"] == "lee2020same" and bib.keys["b"].startswith("lee2020same")
    assert "@article{" in bib.text and "journal = {J. Tests}" in bib.text and "note = {PMID: 7}" in bib.text
    assert r"R\&D\_x 50\% gain" in bib.text and "{x}" not in bib.text
    assert build_bibtex([]).text.strip().endswith("No references were provided.")
    assert SynthesizerAgent.build_bibtex(papers).keys == bib.keys


def test_bib_file_is_written_even_without_papers(tmp_path):
    result, _, out = run(tmp_path, data={**DATA, "papers": []}, llm=FakeLLM({"introduction": "This introduction cites nothing and describes the aim of the study only."}))
    assert "No references were provided" in (out / "references.bib").read_text(encoding="utf-8")
    assert "NO REFERENCES PROVIDED" in (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert result.cited_keys == []


# ---- fabrication guards ------------------------------------------------------------------------
def test_invented_number_is_rejected_then_retried_with_feedback(tmp_path):
    llm = FakeLLM(script={"abstract": ["Model B improves accuracy by 7.3 points over the baseline in this study."]})
    result, _, _ = run(tmp_path, llm=llm)
    assert result.sections["abstract"] == "llm" and llm.calls["abstract"] == 2
    retry_prompt = [p for p in llm.prompts if "SECTION: abstract" in p][1]
    assert "REJECTED" in retry_prompt and "7.3" in retry_prompt


def test_persistent_invention_becomes_a_placeholder_not_fake_text(tmp_path):
    fake = "Model B improves accuracy by 7.3 points over the baseline in this study, a large gain."
    result, _, out = run(tmp_path, llm=FakeLLM(script={"abstract": [fake, fake]}))
    tex = (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert result.status == "partial" and result.sections["abstract"].startswith("placeholder:")
    assert "7.3" not in tex and "ABSTRACT NOT GENERATED" in tex
    assert any("abstract" in w and "placeholder" in w for w in result.warnings)


def test_invented_citation_and_reference_label_are_rejected(tmp_path):
    ctx = _Context({"vaswani2017attention"}, {"tab:results"}, build_allowed_numbers("0.85"), False)
    latex, problems = check_and_render("Prior work \\cite{madeup2099paper} shows many things about this topic here.", ctx)
    assert latex is None and "madeup2099paper" in problems[0]
    latex, problems = check_and_render("As shown in \\ref{fig:nonexistent} the results are clear and strong here.", ctx)
    assert latex is None and "fig:nonexistent" in problems[0]
    ok, _ = check_and_render("Known work \\cite{vaswani2017attention} is relevant to this study on a simple task.", ctx)
    assert ok and ctx.cited == ["vaswani2017attention"]


def test_citing_when_no_papers_supplied_is_rejected(tmp_path):
    llm = FakeLLM(answers={"introduction": "Earlier work \\cite{smith2020} studied this problem for a long time."})
    result, _, _ = run(tmp_path, data={**DATA, "papers": []}, llm=llm)
    assert result.sections["introduction"].startswith("placeholder:") and llm.calls["introduction"] == 2


@pytest.mark.parametrize("evil", [
    "Text here \\input{/etc/passwd} and more words to make the answer long enough to pass.",
    "Text here \\write18{rm -rf /} and more words to make the answer long enough to pass.",
    "\\documentclass{article} and enough extra words to make the answer long enough to pass.",
    "Text \\href{http://evil}{click} and more words to make the answer long enough to pass here.",
])
def test_latex_commands_in_llm_text_are_rejected(evil):
    ctx = _Context(set(), set(), set(), False)
    latex, problems = check_and_render(evil, ctx)
    assert latex is None and "LaTeX commands" in problems[0]


@pytest.mark.parametrize("raw,fragment", [
    ("", "empty"), ("   ", "empty"), (None, "empty"), (123, "empty"),
    ('{"text": "A paragraph that is long enough to look real but it is JSON."}', "JSON"),
    ("# Heading\nSome text that is long enough to be a paragraph of the section.", "Markdown"),
    ("Too short.", "too short"),
])
def test_malformed_model_answers_are_rejected(raw, fragment):
    latex, problems = check_and_render(raw, _Context(set(), set(), set(), False))
    assert latex is None and fragment in problems[0]


def test_special_characters_are_escaped_and_fences_stripped():
    ctx = _Context(set(), set(), build_allowed_numbers("50 5 3"), False)
    latex, _ = check_and_render("```text\nThe gain is 50% for a_b & c# on $5 budgets {x} with 3 runs ok.\n```", ctx)
    assert latex == r"The gain is 50\% for a\_b \& c\# on \$5 budgets \{x\} with 3 runs ok."


def test_rounding_and_percent_forms_are_allowed_but_new_numbers_are_not():
    allowed = build_allowed_numbers("accuracy 0.8589 and n=10")
    assert find_unverified_numbers("0.86 or 0.859 or 85.9 or 86 or 10", allowed) == []
    assert find_unverified_numbers("0.87 and 11 and 3.5", allowed) == ["0.87", "11", "3.5"]
    assert extract_numbers("ResNet50 H2O 1,000 0.5") == [1000.0, 0.5]


def test_missing_markers_are_allowed_and_warned():
    ctx = _Context(set(), set(), set(), False)
    latex, _ = check_and_render("The dataset description is [MISSING: dataset name] in the supplied facts so far.", ctx, "setup")
    assert r"\textbf{[MISSING: dataset name]}" in latex and any("[MISSING" in w for w in ctx.warnings)


def test_unverified_claim_wording_and_significance_are_warned(tmp_path):
    llm = FakeLLM({"conclusion": "This novel method is significant and the finding is limited to a synthetic task."})
    result, _, _ = run(tmp_path, data={**DATA, "results": [DATA["results"][0]]}, llm=llm)
    assert any("'novel'" in w for w in result.warnings) and any("significance" in w for w in result.warnings)


# ---- LLM / API failures ---------------------------------------------------------------------
@pytest.mark.parametrize("error", [LLMError("HTTP 500"), RuntimeError("boom"), ConnectionError("down")])
def test_llm_failures_give_placeholders_and_still_write_files(tmp_path, error):
    llm = FakeLLM(error=error)
    result, _, out = run(tmp_path, llm=llm)
    assert result.status == "placeholders_only" and all(s.startswith("placeholder:") for s in result.sections.values())
    assert (out / "generated_research_paper.tex").is_file() and (out / "references.bib").is_file()
    assert sum(llm.calls.values()) == 5 * 2  # one retry per section
    assert "NOT GENERATED" in (out / "generated_research_paper.tex").read_text(encoding="utf-8")


def test_transient_api_error_is_retried(tmp_path):
    llm = FakeLLM(script={"introduction": [LLMError("rate limited")]})
    result, _, _ = run(tmp_path, llm=llm)
    assert result.sections["introduction"] == "llm" and llm.calls["introduction"] == 2


def test_zero_retries_means_one_attempt(tmp_path):
    llm = FakeLLM(error=RuntimeError("x"))
    run(tmp_path, llm=llm, agent_kw={"max_retries": 0})
    assert sum(llm.calls.values()) == 5


def test_no_llm_configured(tmp_path, monkeypatch):
    for var in ("LLM_API_KEY", "LLM_MODEL", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    agent = SynthesizerAgent(use_env_llm=True)
    assert agent.llm is None
    with pytest.raises(SynthesizerConfigError, match="LLM_API_KEY"):
        agent.synthesize(DATA, tmp_path / "o")
    result = agent.synthesize(DATA, tmp_path / "o", require_llm=False)
    tex = (tmp_path / "o" / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert result.status == "placeholders_only" and "no LLM configured" in tex
    assert "Model B & accuracy" in tex and (tmp_path / "o" / "references.bib").is_file()  # code-built parts still present


# ---- missing values -> placeholders -------------------------------------------------------------
def test_missing_setup_results_figures_and_authors_become_placeholders(tmp_path):
    llm = FakeLLM()
    data = {"title": "Only A Hypothesis", "hypothesis": "A idea to test later."}
    result, _, out = run(tmp_path, data=data, llm=llm)
    tex = (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    for text in ("RESULTS NOT PROVIDED", "NO FIGURES PROVIDED", "AUTHORS MISSING", "NO REFERENCES PROVIDED",
                 "EXPERIMENTAL SETUP NOT GENERATED: no experimental setup was provided",
                 "RESULTS DISCUSSION NOT GENERATED: no verified results were provided"):
        assert text in tex
    assert "experimental_setup" not in llm.calls and "results_discussion" not in llm.calls  # nothing to invent from


def test_title_is_escaped_and_cannot_inject_latex(tmp_path):
    _, _, out = run(tmp_path, data={**DATA, "title": "R&D \\input{secret} 100% _x_"})
    tex = (out / "generated_research_paper.tex").read_text(encoding="utf-8")
    assert r"\title{R\&D \textbackslash{}input\{secret\} 100\% \_x\_}" in tex
    assert latex_escape("a\\b") == "a\\textbackslash{}b"


# ---- real LaTeX compile of generated output (skipped when pdflatex is missing) -------------------------
@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is not installed")
def test_generated_paper_really_compiles(tmp_path):
    img = tmp_path / "f.png"
    img.write_bytes(PNG)
    data = {**DATA, "figures": [{"path": str(img), "caption": "A figure.", "label": "f1"}], "is_simulated": True}
    result, _, out = run(tmp_path, data=data, llm=FakeLLM({"results_discussion": "See \\ref{tab:results} and \\ref{fig:f1} for the accuracy values 0.85 and 0.80."}))
    compiled = compile_pdf(result.tex_path)
    assert compiled.pdf_ok, compiled.message + str(compiled.errors)
    assert (out / "generated_research_paper.pdf").stat().st_size > 1000


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex is not installed")
def test_placeholder_only_draft_compiles(tmp_path):
    result = SynthesizerAgent(use_env_llm=False).synthesize({"title": "Draft", "hypothesis": "H"}, tmp_path, require_llm=False)
    assert compile_pdf(result.tex_path).pdf_ok
