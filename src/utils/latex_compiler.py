"""Local LaTeX -> PDF compiler with a Markdown/HTML fallback.

* ``compile_pdf`` runs ``pdflatex`` (and ``bibtex`` when the paper uses a .bib file).
  A PDF is reported ONLY if the engine succeeded and a fresh PDF file exists.
* ``compile_with_fallback`` additionally writes ``<name>.html`` (MathJax) and
  ``<name>.md`` when the PDF could not be built, so the draft is still readable.
* The fallback converter understands the subset of LaTeX produced by
  ``templates/paper_template.tex`` + ``SynthesizerAgent`` (sections, abstract,
  paragraphs, tables, figures, \\cite, \\ref, inline math). It is not a general
  LaTeX converter.

Works on Windows, macOS and Linux (no shell is used). Install a LaTeX engine with
MiKTeX (https://miktex.org) or TeX Live (https://tug.org/texlive/).
"""

from __future__ import annotations

import html
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

INSTALL_HINT = (
    "Install a LaTeX distribution: MiKTeX (https://miktex.org/download) or TeX Live "
    "(https://tug.org/texlive/), then restart the terminal and check with: pdflatex --version"
)


# --------------------------------------------------------------------------
# Result model
# --------------------------------------------------------------------------
class CompileResult(BaseModel):
    """Outcome of a compilation attempt. ``pdf_path`` is set only when a PDF really exists."""

    status: Literal["pdf_generated", "engine_unavailable", "compile_failed", "invalid_input"]
    message: str
    pdf_path: Optional[str] = None
    engine: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    log_tail: str = ""
    fallback_files: List[str] = Field(default_factory=list)

    @property
    def pdf_ok(self) -> bool:
        return self.status == "pdf_generated" and self.pdf_path is not None


# --------------------------------------------------------------------------
# PDF compilation
# --------------------------------------------------------------------------
def find_engine(name: str = "pdflatex") -> Optional[str]:
    """Return the full path of the LaTeX engine, or None if it is not installed."""
    return shutil.which(name)


def _extract_errors(log: str, limit: int = 6) -> List[str]:
    """Pick the useful error lines out of a LaTeX log."""
    found: List[str] = []
    lines = log.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("!") or re.match(r"^\S+\.tex:\d+:", line):
            context = lines[i + 1].strip() if i + 1 < len(lines) else ""
            found.append(f"{line.strip()} {context}".strip())
            if len(found) >= limit:
                break
    return found


def _run(cmd: List[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, stdin=subprocess.DEVNULL,
    )


def compile_pdf(
    tex_path: str,
    engine: str = "pdflatex",
    timeout: int = 180,
    use_bibtex: bool = True,
) -> CompileResult:
    """Compile ``tex_path`` into a PDF next to it. Never claims success without a fresh PDF."""
    tex = Path(tex_path)
    if not tex.is_file() or tex.suffix.lower() != ".tex":
        return CompileResult(status="invalid_input", message=f"Not a .tex file: {tex_path}")
    tex = tex.resolve()
    engine_path = find_engine(engine)
    if engine_path is None:
        return CompileResult(
            status="engine_unavailable", engine=engine,
            message=f"'{engine}' was not found on this computer, so no PDF was generated. {INSTALL_HINT}",
        )

    pdf = tex.with_suffix(".pdf")
    try:
        if pdf.exists():
            pdf.unlink()  # a stale PDF from an earlier run must never be mistaken for success
    except OSError as exc:
        return CompileResult(
            status="compile_failed", engine=engine, message=f"Could not replace the old PDF ({exc}). "
            "Close it in your PDF viewer and try again.")

    started = time.time()
    tex_cmd = [engine_path, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", tex.name]
    warnings: List[str] = []
    log = ""
    try:
        first = _run(tex_cmd, tex.parent, timeout)
        log = (first.stdout or "") + (first.stderr or "")
        if first.returncode != 0:
            errors = _extract_errors(log)
            hint = ""
            if re.search(r"File `[^']+\.(sty|cls)' not found", log):
                hint = " A LaTeX package is missing; install it (MiKTeX can install packages on demand)."
            return CompileResult(
                status="compile_failed", engine=engine, errors=errors, log_tail=log[-1500:],
                message=f"{engine} failed (exit code {first.returncode}); no PDF was generated.{hint}")

        uses_bib = bool(re.search(r"\\bibliography\{", tex.read_text(encoding="utf-8", errors="replace")))
        passes = 2
        if use_bibtex and uses_bib:
            bibtex = shutil.which("bibtex")
            if bibtex is None:
                warnings.append("bibtex was not found; references may show as [?].")
            else:
                bib = _run([bibtex, tex.stem], tex.parent, timeout)
                if bib.returncode >= 2:
                    warnings.append("bibtex reported errors; check references.bib.")
                passes = 3
        for _ in range(passes - 1):
            nxt = _run(tex_cmd, tex.parent, timeout)
            log = (nxt.stdout or "") + (nxt.stderr or "")
            if nxt.returncode != 0:
                return CompileResult(
                    status="compile_failed", engine=engine, errors=_extract_errors(log), warnings=warnings,
                    log_tail=log[-1500:], message=f"{engine} failed on a later pass; no PDF was generated.")
    except subprocess.TimeoutExpired:
        return CompileResult(status="compile_failed", engine=engine,
                             message=f"{engine} timed out after {timeout} seconds; no PDF was generated.")
    except OSError as exc:
        return CompileResult(status="compile_failed", engine=engine,
                             message=f"Could not run {engine}: {exc}")

    if not pdf.is_file() or pdf.stat().st_size == 0 or pdf.stat().st_mtime < started - 2:
        return CompileResult(status="compile_failed", engine=engine, warnings=warnings, log_tail=log[-1500:],
                             message=f"{engine} finished but no new PDF was produced.")
    for suffix in (".aux", ".log", ".out", ".bbl", ".blg", ".toc"):  # tidy helper files (kept on failure for debugging)
        try:
            tex.with_suffix(suffix).unlink()
        except OSError:
            pass
    return CompileResult(status="pdf_generated", engine=engine, pdf_path=str(pdf), warnings=warnings,
                         message=f"PDF generated: {pdf}")


def compile_with_fallback(
    tex_path: str,
    bib_path: Optional[str] = None,
    engine: str = "pdflatex",
    timeout: int = 180,
) -> CompileResult:
    """Try for a PDF; if that is impossible or fails, write HTML + Markdown fallbacks instead."""
    result = compile_pdf(tex_path, engine=engine, timeout=timeout)
    if result.pdf_ok or result.status == "invalid_input":
        return result
    try:
        files = write_fallback(tex_path, bib_path)
        result.fallback_files = [str(f) for f in files]
        result.message += " Fallback written (HTML with MathJax + Markdown)."
    except Exception as exc:  # fallback problems must not hide the original error
        logger.exception("Fallback generation failed")
        result.warnings.append(f"Fallback generation failed: {exc}")
    return result


# --------------------------------------------------------------------------
# BibTeX reader (small, for the fallback)
# --------------------------------------------------------------------------
def _read_braced(text: str, start: int) -> Tuple[str, int]:
    """Read a {...} group starting at text[start] == '{'. Returns (content, index after '}')."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif text[i] == "}" and (i == 0 or text[i - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def parse_bibtex(text: str) -> Dict[str, Dict[str, str]]:
    """Parse ``@type{key, field = {value}, ...}`` entries into {key: {field: value}}."""
    entries: Dict[str, Dict[str, str]] = {}
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        body, _ = _read_braced(text, text.index("{", m.start()))
        fields: Dict[str, str] = {"type": m.group(1).lower()}
        for fm in re.finditer(r"(\w+)\s*=\s*\{", body):
            value, _ = _read_braced(body, fm.end() - 1)
            fields[fm.group(1).lower()] = value.replace("{", "").replace("}", "").strip()
        entries[m.group(2)] = fields
    return entries


# --------------------------------------------------------------------------
# Fallback: LaTeX subset -> HTML / Markdown
# --------------------------------------------------------------------------
def _strip_comments(tex: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", tex)


def _command_arg(tex: str, name: str) -> Optional[str]:
    m = re.search(r"\\" + name + r"\s*\{", tex)
    return _read_braced(tex, m.end() - 1)[0] if m else None


class _Doc:
    def __init__(self) -> None:
        self.title = ""
        self.authors = ""
        self.blocks: List[tuple] = []  # (kind, payload...)


def _parse_tex(tex_text: str) -> _Doc:
    tex = _strip_comments(tex_text)
    doc = _Doc()
    doc.title = _command_arg(tex, "title") or ""
    doc.authors = _command_arg(tex, "author") or ""
    body = tex.split("\\begin{document}", 1)[-1].split("\\end{document}", 1)[0]
    pattern = re.compile(
        r"\\begin\{abstract\}(?P<abs>.*?)\\end\{abstract\}"
        r"|\\(?P<sec>section|subsection)\*?\{(?P<sectitle>[^{}]*)\}"
        r"|\\begin\{(?P<env>table\*?|figure\*?)\}(?P<envbody>.*?)\\end\{(?P=env)\}"
        r"|\\begin\{(?P<list>itemize|enumerate)\}(?P<listbody>.*?)\\end\{(?P=list)\}"
        r"|\\begin\{center\}(?P<center>.*?)\\end\{center\}"
        r"|\\bibliography\{(?P<bib>[^}]*)\}",
        re.S)

    def paragraphs(chunk: str) -> None:
        chunk = re.sub(r"\\(maketitle|bibliographystyle\{[^}]*\}|twocolumn|onecolumn|clearpage)", "", chunk)
        for para in re.split(r"\n\s*\n", chunk):
            if para.strip():
                doc.blocks.append(("p", para.strip()))

    pos = 0
    for m in pattern.finditer(body):
        paragraphs(body[pos:m.start()])
        pos = m.end()
        if m.group("abs") is not None:
            doc.blocks.append(("abstract", m.group("abs").strip()))
        elif m.group("sec"):
            doc.blocks.append((m.group("sec"), m.group("sectitle")))
        elif m.group("env"):
            env = m.group("envbody")
            caption = _command_arg(env, "caption") or ""
            label = _command_arg(env, "label") or ""
            if m.group("env").startswith("table"):
                rows: List[List[str]] = []
                tab = re.search(r"\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}", env, re.S)
                if tab:
                    cleaned = re.sub(r"\\(toprule|midrule|bottomrule|hline)", "", tab.group(1))
                    for row in re.split(r"\\\\", cleaned):
                        if row.strip():
                            rows.append([c.strip() for c in re.split(r"(?<!\\)&", row)])
                doc.blocks.append(("table", caption, label, rows))
            else:
                img = re.search(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}", env)
                doc.blocks.append(("figure", caption, label, img.group(1) if img else ""))
        elif m.group("list"):
            items = [i.strip() for i in re.split(r"\\item", m.group("listbody")) if i.strip()]
            doc.blocks.append(("list", items))
        elif m.group("center") is not None:
            doc.blocks.append(("p", m.group("center").strip()))
        elif m.group("bib") is not None:
            doc.blocks.append(("bibliography",))
    paragraphs(body[pos:])
    return doc


def _inline(text: str, fmt: str, refs: Dict[str, str], cite_numbers: Dict[str, int]) -> str:
    """Convert LaTeX inline markup to HTML (fmt='html') or Markdown (fmt='md')."""
    stash: List[str] = []

    def keep(value: str) -> str:
        stash.append(value)
        return f"\x00{len(stash) - 1}\x00"

    esc = (lambda s: html.escape(s, quote=False)) if fmt == "html" else (lambda s: s)
    text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$",
                  lambda m: keep(f"\\({esc(m.group(1))}\\)" if fmt == "html" else f"${m.group(1)}$"), text, flags=re.S)
    literals = {r"\textbackslash{}": "\\", r"\textasciitilde{}": "~", r"\%": "%", r"\&": "&", r"\_": "_",
                r"\#": "#", r"\$": "$", r"\{": "{", r"\}": "}"}
    for tex_form, char in literals.items():
        text = text.replace(tex_form, keep(esc(char)))
    text = text.replace("---", "\u2014").replace("--", "\u2013").replace("~", " ")
    text = re.sub(r"\\\\\s*", "\n", text)
    text = esc(text)

    def cite(m: re.Match) -> str:
        nums = [str(cite_numbers.get(k.strip(), "?")) for k in m.group(1).split(",")]
        return "[" + ", ".join(nums) + "]"

    text = re.sub(r"\\cite[tp]?\{([^}]*)\}", cite, text)
    text = re.sub(r"\\ref\{([^}]*)\}", lambda m: refs.get(m.group(1), "?"), text)
    wrap = {"html": {"textbf": "<strong>{}</strong>", "emph": "<em>{}</em>", "textit": "<em>{}</em>",
                     "texttt": "<code>{}</code>"},
            "md": {"textbf": "**{}**", "emph": "*{}*", "textit": "*{}*", "texttt": "`{}`"}}[fmt]
    previous = None
    while previous != text:  # repeat so nested commands resolve from the inside out
        previous = text
        text = re.sub(r"\\(textbf|emph|textit|texttt)\{([^{}]*)\}",
                      lambda m: wrap[m.group(1)].format(m.group(2)), text)
    text = re.sub(r"\\url\{([^{}]*)\}",
                  lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>' if fmt == "html" else m.group(1), text)
    text = re.sub(r"\\[a-zA-Z]+\*?", "", text)  # drop any other command (e.g. \small, \today)
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text).strip()


def _prepare(tex_text: str, bib_text: Optional[str]):
    doc = _parse_tex(tex_text)
    refs: Dict[str, str] = {}
    counters = {"table": 0, "figure": 0}
    for block in doc.blocks:
        if block[0] in ("table", "figure"):
            counters[block[0]] += 1
            if block[2]:
                refs[block[2]] = str(counters[block[0]])
    cites: List[str] = []
    for key_group in re.findall(r"\\cite[tp]?\{([^}]*)\}", _strip_comments(tex_text)):
        for key in key_group.split(","):
            if key.strip() and key.strip() not in cites:
                cites.append(key.strip())
    cite_numbers = {k: i + 1 for i, k in enumerate(cites)}
    bib = parse_bibtex(bib_text) if bib_text else {}
    return doc, refs, cite_numbers, cites, bib


def _reference_line(key: str, entry: Dict[str, str]) -> str:
    if not entry:
        return f"{key} (not found in references.bib)"
    parts = [entry.get("author", ""), f"\u201c{entry['title']}\u201d" if entry.get("title") else "",
             entry.get("journal", ""), entry.get("year", ""), entry.get("url", "")]
    return ". ".join(p for p in parts if p)


def tex_to_html(tex_text: str, bib_text: Optional[str] = None) -> str:
    """Render a template-style paper as a self-contained HTML page with MathJax."""
    doc, refs, nums, cites, bib = _prepare(tex_text, bib_text)
    inl = lambda s: _inline(s, "html", refs, nums)  # noqa: E731
    authors_html = inl(doc.authors).replace("\n", "<br>")
    out = [f"<h1>{inl(doc.title)}</h1>", f'<p class="authors">{authors_html}</p>']
    t_no = f_no = 0
    for block in doc.blocks:
        kind = block[0]
        if kind == "abstract":
            out.append(f'<div class="abstract"><h2>Abstract</h2><p>{inl(block[1])}</p></div>')
        elif kind == "section":
            out.append(f"<h2>{inl(block[1])}</h2>")
        elif kind == "subsection":
            out.append(f"<h3>{inl(block[1])}</h3>")
        elif kind == "p":
            out.append("<p>" + inl(block[1]).replace("\n", "<br>") + "</p>")
        elif kind == "list":
            out.append("<ul>" + "".join(f"<li>{inl(i)}</li>" for i in block[1]) + "</ul>")
        elif kind == "table":
            t_no += 1
            rows = block[3]
            head = "".join(f"<th>{inl(c)}</th>" for c in rows[0]) if rows else ""
            body = "".join("<tr>" + "".join(f"<td>{inl(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f"<table><caption>Table {t_no}. {inl(block[1])}</caption><thead><tr>{head}</tr></thead>"
                       f"<tbody>{body}</tbody></table>")
        elif kind == "figure":
            f_no += 1
            out.append(f'<figure><img src="{html.escape(block[3])}" alt="Figure {f_no}">'
                       f"<figcaption>Figure {f_no}. {inl(block[1])}</figcaption></figure>")
        elif kind == "bibliography" and cites:
            items = "".join(f"<li>{html.escape(_reference_line(k, bib.get(k, {})))}</li>" for k in cites)
            out.append(f"<h2>References</h2><ol>{items}</ol>")
    style = ("body{font-family:Georgia,serif;max-width:48rem;margin:2rem auto;padding:0 1rem;line-height:1.5}"
             "table{border-collapse:collapse;margin:1rem 0}th,td{border-top:1px solid #444;padding:.25rem .7rem}"
             "caption,figcaption{font-size:.9rem;margin:.4rem 0}img{max-width:100%}.abstract{margin:1rem 2rem}")
    mathjax = ("<script>window.MathJax={tex:{inlineMath:[['\\\\(','\\\\)']]}};</script>"
               '<script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>')
    plain_title = re.sub(r"<[^>]+>", "", inl(doc.title))  # inl() already escaped it
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>{plain_title}</title>'
            f"<style>{style}</style>{mathjax}</head><body>{''.join(out)}</body></html>")


def tex_to_markdown(tex_text: str, bib_text: Optional[str] = None) -> str:
    """Render a template-style paper as Markdown (inline math kept as $...$)."""
    doc, refs, nums, cites, bib = _prepare(tex_text, bib_text)
    inl = lambda s: _inline(s, "md", refs, nums)  # noqa: E731
    out = [f"# {inl(doc.title)}", "", inl(doc.authors).replace("\n", "  \n"), ""]
    t_no = f_no = 0
    for block in doc.blocks:
        kind = block[0]
        if kind == "abstract":
            out += ["## Abstract", "", inl(block[1]), ""]
        elif kind == "section":
            out += [f"## {inl(block[1])}", ""]
        elif kind == "subsection":
            out += [f"### {inl(block[1])}", ""]
        elif kind == "p":
            out += [inl(block[1]), ""]
        elif kind == "list":
            out += [f"- {inl(i)}" for i in block[1]] + [""]
        elif kind == "table":
            t_no += 1
            rows = [[inl(c) for c in r] for r in block[3]]
            if rows:
                out += [f"**Table {t_no}.** {inl(block[1])}", "", "| " + " | ".join(rows[0]) + " |",
                        "|" + "---|" * len(rows[0])] + ["| " + " | ".join(r) + " |" for r in rows[1:]] + [""]
        elif kind == "figure":
            f_no += 1
            out += [f"![Figure {f_no}]({block[3]})", "", f"**Figure {f_no}.** {inl(block[1])}", ""]
        elif kind == "bibliography" and cites:
            out += ["## References", ""] + [f"{i}. {_reference_line(k, bib.get(k, {}))}"
                                            for i, k in enumerate(cites, 1)] + [""]
    return "\n".join(out)


def write_fallback(tex_path: str, bib_path: Optional[str] = None) -> List[Path]:
    """Write ``<name>.html`` and ``<name>.md`` next to the .tex file. Returns the files written."""
    tex = Path(tex_path)
    tex_text = tex.read_text(encoding="utf-8")
    if bib_path is None and (tex.parent / "references.bib").is_file():
        bib_path = str(tex.parent / "references.bib")
    bib_text = Path(bib_path).read_text(encoding="utf-8") if bib_path and Path(bib_path).is_file() else None
    html_file, md_file = tex.with_suffix(".html"), tex.with_suffix(".md")
    html_file.write_text(tex_to_html(tex_text, bib_text), encoding="utf-8")
    md_file.write_text(tex_to_markdown(tex_text, bib_text), encoding="utf-8")
    return [html_file, md_file]
