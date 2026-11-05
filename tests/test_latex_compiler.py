"""Tests for src/utils/latex_compiler.py.

Most tests mock the LaTeX engine, so they run without LaTeX installed. Two
integration tests run the real pdflatex and are skipped when it is missing."""
import subprocess
from pathlib import Path

import pytest

from src.utils import latex_compiler as lc
from src.utils.latex_compiler import (
    compile_pdf, compile_with_fallback, find_engine, parse_bibtex, tex_to_html, tex_to_markdown, write_fallback,
)

TEX = r"""\documentclass{article}
\title{My <Title> \& More}
\author{A. Author \\ Lab}
\begin{document}
\maketitle
\begin{abstract}We study $x^2$ with \cite{key1}.\end{abstract}
\section{Intro}
Text with 50\% and \textbf{bold}, see Table~\ref{tab:r}. <script>alert(1)</script>

\begin{table}[t]\centering\caption{Results.}\label{tab:r}
\begin{tabular}{ll}\toprule A & B \\ \midrule 1 & 2 \\ \bottomrule\end{tabular}\end{table}
\begin{figure}[t]\centering\includegraphics{figures/f.png}\caption{A fig.}\label{fig:1}\end{figure}
\bibliographystyle{ieeetr}\bibliography{references}
\end{document}
"""
BIB = "@misc{key1,\n author = {Jane Doe and John Roe},\n title = {{A Title}},\n year = {2020},\n url = {https://example.org}\n}\n"
HAS_PDFLATEX = find_engine("pdflatex") is not None


@pytest.fixture
def tex_file(tmp_path):
    path = tmp_path / "paper.tex"
    path.write_text(TEX, encoding="utf-8")
    (tmp_path / "references.bib").write_text(BIB, encoding="utf-8")
    return path


def fake_engine(monkeypatch, make_pdf=True, returncode=0, stdout="", pdf_bytes=b"%PDF-1.5 fake"):
    """Replace the engine lookup and subprocess runner. Returns the list of commands that were run."""
    calls = []
    monkeypatch.setattr(lc, "find_engine", lambda name="pdflatex": "/fake/" + name)
    monkeypatch.setattr(lc.shutil, "which", lambda name: "/fake/" + name)

    def run(cmd, cwd, timeout):
        calls.append(cmd)
        if make_pdf and returncode == 0 and "pdflatex" in cmd[0]:
            Path(cwd, Path(cmd[-1]).stem + ".pdf").write_bytes(pdf_bytes)
        return subprocess.CompletedProcess(cmd, returncode, stdout, "")

    monkeypatch.setattr(lc, "_run", run)
    return calls


# ---- engine lookup / invalid input -----------------------------------------------------
def test_find_engine_uses_path_lookup(monkeypatch):
    monkeypatch.setattr(lc.shutil, "which", lambda name: "/usr/bin/" + name if name == "pdflatex" else None)
    assert find_engine("pdflatex") == "/usr/bin/pdflatex" and find_engine("nope") is None


@pytest.mark.parametrize("name", ["missing.tex", "paper.txt"])
def test_invalid_input_is_reported_without_crashing(tmp_path, name):
    (tmp_path / "paper.txt").write_text("x")
    result = compile_pdf(str(tmp_path / name))
    assert result.status == "invalid_input" and not result.pdf_ok and result.pdf_path is None


# ---- engine unavailable -------------------------------------------------------------------
def test_missing_engine_does_not_claim_a_pdf(tex_file, monkeypatch):
    monkeypatch.setattr(lc, "find_engine", lambda name="pdflatex": None)
    result = compile_pdf(str(tex_file))
    assert result.status == "engine_unavailable" and not result.pdf_ok and result.pdf_path is None
    assert "no PDF was generated" in result.message and "MiKTeX" in result.message
    assert not tex_file.with_suffix(".pdf").exists()


# ---- success and failure (mocked engine) ---------------------------------------------------------
def test_success_runs_pdflatex_bibtex_pdflatex_pdflatex(tex_file, monkeypatch):
    calls = fake_engine(monkeypatch)
    result = compile_pdf(str(tex_file))
    assert result.pdf_ok and result.status == "pdf_generated" and Path(result.pdf_path).is_file()
    assert [Path(c[0]).name for c in calls] == ["pdflatex", "bibtex", "pdflatex", "pdflatex"]
    assert "-halt-on-error" in calls[0] and calls[0][-1] == "paper.tex"


def test_no_bibtex_run_when_paper_has_no_bibliography(tmp_path, monkeypatch):
    path = tmp_path / "p.tex"
    path.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")
    calls = fake_engine(monkeypatch)
    assert compile_pdf(str(path)).pdf_ok and len(calls) == 2 and all("bibtex" not in c[0] for c in calls)


def test_missing_bibtex_is_a_warning_not_a_failure(tex_file, monkeypatch):
    fake_engine(monkeypatch)
    monkeypatch.setattr(lc.shutil, "which", lambda name: None)
    result = compile_pdf(str(tex_file))
    assert result.pdf_ok and any("bibtex was not found" in w for w in result.warnings)


def test_compile_error_reports_latex_errors_and_no_pdf(tex_file, monkeypatch):
    fake_engine(monkeypatch, returncode=1, stdout="./paper.tex:12: Undefined control sequence.\n! Undefined control sequence.\nl.12 \\foo\n")
    result = compile_pdf(str(tex_file))
    assert result.status == "compile_failed" and not result.pdf_ok and result.pdf_path is None
    assert any("Undefined control sequence" in e for e in result.errors)
    assert not tex_file.with_suffix(".pdf").exists()


def test_missing_package_gives_a_hint(tex_file, monkeypatch):
    fake_engine(monkeypatch, returncode=1, stdout="! LaTeX Error: File `foo.sty' not found.\n")
    assert "package is missing" in compile_pdf(str(tex_file)).message


def test_stale_pdf_is_never_mistaken_for_success(tex_file, monkeypatch):
    tex_file.with_suffix(".pdf").write_bytes(b"%PDF old")
    fake_engine(monkeypatch, make_pdf=False)  # engine "succeeds" but writes nothing
    result = compile_pdf(str(tex_file))
    assert result.status == "compile_failed" and not result.pdf_ok and "no new PDF" in result.message
    assert not tex_file.with_suffix(".pdf").exists()


def test_timeout_and_os_errors_are_handled(tex_file, monkeypatch):
    fake_engine(monkeypatch)
    for error, text in [(subprocess.TimeoutExpired("pdflatex", 5), "timed out"), (OSError("boom"), "Could not run")]:
        def run(cmd, cwd, timeout, error=error):
            raise error
        monkeypatch.setattr(lc, "_run", run)
        result = compile_pdf(str(tex_file))
        assert result.status == "compile_failed" and text in result.message and not result.pdf_ok


def test_later_pass_failure_is_reported(tex_file, monkeypatch):
    state = {"n": 0}
    monkeypatch.setattr(lc, "find_engine", lambda name="pdflatex": "/fake/pdflatex")
    monkeypatch.setattr(lc.shutil, "which", lambda name: "/fake/" + name)

    def run(cmd, cwd, timeout):
        state["n"] += 1
        return subprocess.CompletedProcess(cmd, 1 if state["n"] == 3 else 0, "! Emergency stop.\n" if state["n"] == 3 else "", "")

    monkeypatch.setattr(lc, "_run", run)
    result = compile_pdf(str(tex_file))
    assert result.status == "compile_failed" and "later pass" in result.message


# ---- fallback output -------------------------------------------------------------------------------
def test_html_fallback_has_mathjax_structure_and_escapes_html():
    html_text = tex_to_html(TEX, BIB)
    assert "mathjax" in html_text.lower() and r"\(x^2\)" in html_text
    assert "<h1>My &lt;Title&gt; &amp; More</h1>" in html_text and "<title>My &lt;Title&gt; &amp; More</title>" in html_text
    assert "<h2>Abstract</h2>" in html_text and "<h2>Intro</h2>" in html_text
    assert "<script>alert(1)</script>" not in html_text and "&lt;script&gt;" in html_text  # no injection
    assert "<table>" in html_text and "<th>A</th>" in html_text and "<strong>bold</strong>" in html_text
    assert "see Table 1" in html_text and "50%" in html_text and "[1]" in html_text
    assert "Jane Doe and John Roe" in html_text and 'src="figures/f.png"' in html_text


def test_markdown_fallback():
    md = tex_to_markdown(TEX, BIB)
    assert md.startswith("# My <Title> & More") and "## Abstract" in md and "## Intro" in md
    assert "$x^2$" in md and "| A | B |" in md and "**bold**" in md and "![Figure 1](figures/f.png)" in md
    assert "1. Jane Doe and John Roe" in md


def test_citation_missing_from_bib_is_still_listed():
    html_text = tex_to_html(TEX, None)
    assert "key1 (not found in references.bib)" in html_text


def test_parse_bibtex_handles_nested_braces():
    entries = parse_bibtex(BIB + "@article{k2, title={{Deep {NLP}}}, year={2021}}")
    assert entries["key1"]["author"] == "Jane Doe and John Roe" and entries["k2"]["year"] == "2021"
    assert "NLP" in entries["k2"]["title"] and parse_bibtex("") == {}


def test_write_fallback_creates_html_and_markdown(tex_file):
    files = write_fallback(str(tex_file), str(tex_file.parent / "references.bib"))
    assert {f.suffix for f in files} == {".html", ".md"} and all(f.is_file() for f in files)
    assert "MathJax" in tex_file.with_suffix(".html").read_text(encoding="utf-8")


def test_compile_with_fallback_when_engine_missing(tex_file, monkeypatch):
    monkeypatch.setattr(lc, "find_engine", lambda name="pdflatex": None)
    result = compile_with_fallback(str(tex_file), str(tex_file.parent / "references.bib"))
    assert not result.pdf_ok and result.pdf_path is None and result.status == "engine_unavailable"
    assert len(result.fallback_files) == 2 and "Fallback written" in result.message
    assert tex_file.with_suffix(".html").is_file() and tex_file.with_suffix(".md").is_file()


def test_compile_with_fallback_after_compile_error(tex_file, monkeypatch):
    fake_engine(monkeypatch, returncode=1, stdout="! Missing $ inserted.\n")
    result = compile_with_fallback(str(tex_file))
    assert result.status == "compile_failed" and not result.pdf_ok and len(result.fallback_files) == 2


def test_no_fallback_needed_when_pdf_succeeds_and_none_for_invalid_input(tex_file, monkeypatch, tmp_path):
    fake_engine(monkeypatch)
    ok = compile_with_fallback(str(tex_file))
    assert ok.pdf_ok and ok.fallback_files == [] and not tex_file.with_suffix(".html").exists()
    bad = compile_with_fallback(str(tmp_path / "nope.tex"))
    assert bad.status == "invalid_input" and bad.fallback_files == []


def test_fallback_failure_does_not_hide_the_compile_error(tex_file, monkeypatch):
    monkeypatch.setattr(lc, "find_engine", lambda name="pdflatex": None)
    monkeypatch.setattr(lc, "write_fallback", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    result = compile_with_fallback(str(tex_file))
    assert result.status == "engine_unavailable" and any("disk full" in w for w in result.warnings)


# ---- real pdflatex (skipped when LaTeX is not installed) -----------------------------------------------
@pytest.mark.skipif(not HAS_PDFLATEX, reason="pdflatex is not installed")
def test_real_pdflatex_builds_a_pdf(tmp_path):
    path = tmp_path / "ok.tex"
    path.write_text(r"\documentclass{article}\begin{document}Hello $x^2$.\end{document}")
    result = compile_pdf(str(path))
    assert result.pdf_ok and Path(result.pdf_path).read_bytes().startswith(b"%PDF")


@pytest.mark.skipif(not HAS_PDFLATEX, reason="pdflatex is not installed")
def test_real_pdflatex_failure_creates_no_pdf(tmp_path):
    path = tmp_path / "bad.tex"
    path.write_text(r"\documentclass{article}\begin{document}\undefinedcommand\end{document}")
    result = compile_pdf(str(path))
    assert result.status == "compile_failed" and not result.pdf_ok and not path.with_suffix(".pdf").exists()
    assert any("Undefined control sequence" in e for e in result.errors)


@pytest.mark.skipif(not HAS_PDFLATEX, reason="pdflatex is not installed")
def test_helper_files_are_removed_after_success(tmp_path):
    path = tmp_path / "ok.tex"
    path.write_text(r"\documentclass{article}\begin{document}Hi\end{document}")
    assert compile_pdf(str(path)).pdf_ok
    assert sorted(f.name for f in tmp_path.iterdir()) == ["ok.pdf", "ok.tex"]
