"""SynthesizerAgent: turn VERIFIED experimental results into a LaTeX paper draft + references.bib.

Design rules (the reason this module is written the way it is):

* The LLM only writes prose. Numbers, p-values, the results table, figures and
  the BibTeX file are produced by code from the supplied data.
* Every LLM answer is checked before use: citation keys and \\ref labels must
  exist, every number must come from the supplied data, and only \\cite / \\ref
  commands are allowed. A rejected answer is retried once, then replaced by a
  clearly marked placeholder. Nothing is repaired silently.
* Missing information becomes a visible placeholder such as
  ``[RESULTS NOT PROVIDED]``; invalid information (NaN, p-value 1.7, a figure
  file that does not exist) is an input-validation error.
* LLM text is escaped before it reaches LaTeX, so model output cannot inject
  LaTeX commands (e.g. \\input).

LLM configuration is shared with the Hypothesis agent: LLM_PROVIDER, LLM_API_KEY,
LLM_MODEL (and optional LLM_BASE_URL). Any object with ``complete(prompt) -> str``
can be passed as ``llm`` instead.
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

try:  # reuse the project's existing LLM provider configuration (Week 2)
    from src.agents.hypothesis_agent import LLMClient, LLMError, llm_client_from_env
except ImportError:  # pragma: no cover - keeps this module importable on its own
    LLMClient = Any  # type: ignore[misc,assignment]

    class LLMError(RuntimeError):  # type: ignore[no-redef]
        """Raised when the LLM provider call fails."""

    llm_client_from_env = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "paper_template.tex"
REQUIRED_PLACEHOLDERS = (
    "TITLE", "AUTHORS", "DRAFT_NOTICE", "ABSTRACT", "INTRODUCTION", "EXPERIMENTAL_SETUP",
    "RESULTS_TABLE", "RESULTS_DISCUSSION", "FIGURES", "CONCLUSION", "BIBLIOGRAPHY",
)
SECTIONS = ("abstract", "introduction", "experimental_setup", "results_discussion", "conclusion")


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------
class SynthesizerError(Exception):
    """Base class for synthesizer errors."""


class InputValidationError(SynthesizerError, ValueError):
    """The supplied research data is invalid. ``problems`` lists every issue found."""

    def __init__(self, problems: List[str]) -> None:
        self.problems = problems
        super().__init__("Invalid research input: " + "; ".join(problems))


class SynthesizerConfigError(SynthesizerError):
    """No LLM is configured (and placeholders were not explicitly allowed)."""


class TemplateError(SynthesizerError):
    """The LaTeX template is missing or lacks required placeholders."""


# --------------------------------------------------------------------------
# Input models
# --------------------------------------------------------------------------
class Author(BaseModel):
    name: str
    affiliation: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("author name must not be blank")
        return v.strip()


class ResultRow(BaseModel):
    """One verified measurement. ``p_value`` compares this row with ``comparison``."""

    method: str
    metric: str
    value: float
    std: Optional[float] = None
    n: Optional[int] = None
    p_value: Optional[float] = None
    comparison: Optional[str] = None

    @field_validator("method", "metric")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("value", "std", "p_value")
    @classmethod
    def _finite(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v

    @field_validator("std")
    @classmethod
    def _std_non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("std must be >= 0")
        return v

    @field_validator("p_value")
    @classmethod
    def _p_range(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("p_value must be between 0 and 1")
        return v

    @field_validator("n")
    @classmethod
    def _n_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("n must be >= 1")
        return v


class FigureInput(BaseModel):
    path: str
    caption: Optional[str] = None
    label: Optional[str] = None


class PaperMeta(BaseModel):
    """Metadata of a retrieved paper that may be cited. Accepts Week 1 style records."""

    paper_id: str
    title: str = ""
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    venue: Optional[str] = None
    abstract: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if not d.get("paper_id"):
            if d.get("arxiv_id"):
                d["paper_id"] = f"arxiv:{d['arxiv_id']}"
            elif d.get("pmid"):
                d["paper_id"] = f"pubmed:{d['pmid']}"
            elif d.get("id"):
                d["paper_id"] = str(d["id"])
        if d.get("year") is None and d.get("published"):
            m = re.match(r"\d{4}", str(d["published"]))
            if m:
                d["year"] = int(m.group())
        if not d.get("venue") and d.get("journal"):
            d["venue"] = d["journal"]
        return d

    @field_validator("year")
    @classmethod
    def _year_range(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not 1000 <= v <= 2200:
            raise ValueError("year looks invalid")
        return v


class PaperInput(BaseModel):
    """Everything the synthesizer needs. Results must already be verified upstream."""

    title: str
    authors: List[Author] = Field(default_factory=list)
    hypothesis: Optional[str] = None
    experimental_setup: Optional[str] = None
    results: List[ResultRow] = Field(default_factory=list)
    figures: List[FigureInput] = Field(default_factory=list)
    papers: List[PaperMeta] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    is_simulated: bool = False

    @field_validator("authors", mode="before")
    @classmethod
    def _authors_from_strings(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [{"name": a} if isinstance(a, str) else a for a in v]
        return v

    @field_validator("experimental_setup", mode="before")
    @classmethod
    def _setup_from_dict(cls, v: Any) -> Any:
        if isinstance(v, dict):
            return "\n".join(f"{k}: {val}" for k, val in v.items())
        return v

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("title must not be blank")
        return v.strip()

    @model_validator(mode="after")
    def _cross_checks(self) -> "PaperInput":
        problems: List[str] = []
        if not self.results and not (self.hypothesis or "").strip():
            problems.append("provide verified results and/or a hypothesis; there is nothing to write about")
        labels = [f.label for f in self.figures if f.label]
        if len(labels) != len(set(labels)):
            problems.append("figure labels must be unique")
        for fig in self.figures:
            path = Path(fig.path)
            if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".pdf"):
                problems.append(f"figure {fig.path!r} must be a .png, .jpg or .pdf file")
            elif not path.is_file():
                problems.append(f"figure file not found: {fig.path!r}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


def validate_paper_input(data: Union[PaperInput, Dict[str, Any]]) -> PaperInput:
    """Return a validated PaperInput or raise InputValidationError listing every problem."""
    if isinstance(data, PaperInput):
        return data
    if not isinstance(data, dict):
        raise InputValidationError(["input must be a dict or PaperInput"])
    try:
        return PaperInput.model_validate(data)
    except ValidationError as exc:
        problems = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"])
            msg = err["msg"].removeprefix("Value error, ")
            problems.append(f"{where}: {msg}" if where else msg)
        raise InputValidationError(problems) from exc


# --------------------------------------------------------------------------
# Output model
# --------------------------------------------------------------------------
class SynthesisResult(BaseModel):
    """What happened. ``sections`` says per section whether the LLM wrote it or a placeholder was used."""

    status: Literal["complete", "partial", "placeholders_only"]
    tex_path: str
    bib_path: str
    sections: Dict[str, str]
    cited_keys: List[str] = Field(default_factory=list)
    bib_keys: Dict[str, str] = Field(default_factory=dict)
    figures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    is_simulated: bool = False


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
_UNICODE_TO_LATEX = {
    "\u2013": "--", "\u2014": "---", "\u2018": "`", "\u2019": "'", "\u201c": "``", "\u201d": "''",
    "\u2265": r"$\geq$", "\u2264": r"$\leq$", "\u00d7": r"$\times$", "\u00b1": r"$\pm$",
    "\u2192": r"$\rightarrow$", "\u2248": r"$\approx$", "\u00b0": r"$^\circ$", "\u2026": r"\ldots{}",
    "\u00a0": "~", "\u2212": "-",
}
_SPECIALS = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
             "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def latex_escape(text: str) -> str:
    """Escape plain text for LaTeX (and map a few common Unicode symbols)."""
    escaped = re.sub(r"[\\&%$#_{}~^]", lambda m: _SPECIALS[m.group()], text)
    for char, repl in _UNICODE_TO_LATEX.items():
        escaped = escaped.replace(char, repl)
    return escaped


def fmt_number(x: float) -> str:
    """Format a measured value without inventing precision (max 4 decimals)."""
    text = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def fmt_p(p: float) -> str:
    """p-values below 0.001 are reported as '<0.001', others with 3 decimals."""
    return "<0.001" if p < 0.001 else f"{p:.3f}"


_NUMBER = re.compile(r"(?<![A-Za-z_\d.])[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![A-Za-z_\d])")


def extract_numbers(text: str) -> List[float]:
    """All standalone numbers in ``text`` (identifiers such as ResNet50 or H2O are ignored)."""
    out: List[float] = []
    for m in _NUMBER.finditer(text):
        try:
            out.append(float(m.group().replace(",", "")))
        except ValueError:
            continue
    return out


def _variants(a: float) -> Set[float]:
    """Faithful re-statements of a: rounding, and percent form for values in [-1, 1]."""
    values = {round(a, k) for k in range(0, 5)} | {round(a, 6)}
    if abs(a) <= 1:
        values |= {round(a * 100, k) for k in range(0, 3)}
    return values


def build_allowed_numbers(*texts: str) -> Set[float]:
    allowed: Set[float] = set()
    for text in texts:
        for number in extract_numbers(text):
            allowed |= _variants(number)
    return allowed


def find_unverified_numbers(text: str, allowed: Set[float]) -> List[str]:
    """Numbers in ``text`` that do not appear in (or round from) the supplied data."""
    return [m.group() for m in _NUMBER.finditer(text)
            if round(float(m.group().replace(",", "")), 6) not in allowed]


# --------------------------------------------------------------------------
# BibTeX
# --------------------------------------------------------------------------
class BibResult(BaseModel):
    text: str
    keys: Dict[str, str] = Field(default_factory=dict)  # paper_id -> citation key
    warnings: List[str] = Field(default_factory=list)


_TITLE_STOP = {"the", "a", "an", "on", "of", "for", "and", "with", "from", "using", "in", "to", "is", "are"}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _bib_escape(text: str) -> str:
    text = text.replace("\\", " ").replace("{", "").replace("}", "")
    text = re.sub(r"[&%$#_]", lambda m: "\\" + m.group(), text)
    text = text.replace("~", " ").replace("^", " ")
    return " ".join(text.split())


def _make_key(paper: PaperMeta, used: Set[str]) -> str:
    first = paper.authors[0].strip() if paper.authors else ""
    last = first.split(",")[0] if "," in first else (first.split()[-1] if first.split() else "")
    words = [w for w in re.findall(r"[A-Za-z0-9]+", _ascii(paper.title)) if w.lower() not in _TITLE_STOP]
    base = (re.sub(r"[^a-z0-9]", "", _ascii(last).lower()) or "anon") + (str(paper.year) if paper.year else "nd") \
        + (words[0].lower()[:12] if words else "paper")
    key, suffix = base, 0
    while key in used:
        suffix += 1
        key = base + chr(ord("a") + (suffix - 1) % 26) * ((suffix - 1) // 26 + 1)
    used.add(key)
    return key


def build_bibtex(papers: List[PaperMeta]) -> BibResult:
    """Create references.bib text from retrieved paper metadata. Never fills in missing facts."""
    header = "% Generated from retrieved paper metadata. Missing fields are marked [..] and were NOT guessed.\n"
    entries: List[str] = []
    keys: Dict[str, str] = {}
    warnings: List[str] = []
    used: Set[str] = set()
    for paper in papers:
        if paper.paper_id in keys:
            warnings.append(f"duplicate paper {paper.paper_id} ignored in references.bib")
            continue
        if not paper.title.strip():
            warnings.append(f"paper {paper.paper_id} has no title, so it cannot be cited and was left out")
            continue
        key = _make_key(paper, used)
        keys[paper.paper_id] = key
        pid = paper.paper_id.lower()
        is_arxiv = pid.startswith("arxiv:") or "arxiv.org" in (paper.url or "").lower()
        is_pubmed = pid.startswith("pubmed:")
        entry_type = "article" if (is_pubmed and paper.venue) else "misc"
        fields = [
            ("author", " and ".join(_bib_escape(a) for a in paper.authors) if paper.authors else "[AUTHORS MISSING]"),
            ("title", "{" + _bib_escape(paper.title) + "}"),
            ("year", str(paper.year) if paper.year else "n.d."),
        ]
        if entry_type == "article":
            fields.append(("journal", _bib_escape(paper.venue or "")))
        elif paper.venue:
            fields.append(("howpublished", _bib_escape(paper.venue)))
        if is_arxiv and pid.startswith("arxiv:"):
            fields += [("eprint", _bib_escape(paper.paper_id.split(":", 1)[1])), ("archivePrefix", "arXiv")]
        if is_pubmed:
            fields.append(("note", "PMID: " + _bib_escape(paper.paper_id.split(":", 1)[1])))
        if paper.doi:
            fields.append(("doi", _bib_escape(paper.doi)))
        if paper.url:
            fields.append(("url", paper.url.strip().replace("{", "").replace("}", "")))
        if not paper.authors:
            warnings.append(f"paper {paper.paper_id} has no authors; marked [AUTHORS MISSING]")
        if not paper.year:
            warnings.append(f"paper {paper.paper_id} has no year; marked n.d.")
        body = ",\n".join(f"  {name} = {{{value}}}" for name, value in fields)
        entries.append(f"@{entry_type}{{{key},\n{body}\n}}")
    text = header + ("\n\n".join(entries) + "\n" if entries else "% No references were provided.\n")
    return BibResult(text=text, keys=keys, warnings=warnings)


# --------------------------------------------------------------------------
# Template handling
# --------------------------------------------------------------------------
def load_template(path: Optional[Union[str, Path]] = None) -> str:
    """Read the LaTeX template and check that every required placeholder is present."""
    template_path = Path(path) if path else DEFAULT_TEMPLATE
    if not template_path.is_file():
        raise TemplateError(f"LaTeX template not found: {template_path}")
    raw = template_path.read_text(encoding="utf-8")
    # Comment-only lines may mention placeholders for humans; drop them so they are never filled in.
    text = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("%")) + "\n"
    missing = [p for p in REQUIRED_PLACEHOLDERS if f"<<{p}>>" not in text]
    if missing:
        raise TemplateError(f"Template is missing placeholder(s): {', '.join('<<' + m + '>>' for m in missing)}")
    return text


def render_template(template: str, values: Dict[str, str]) -> str:
    """Fill every <<NAME>> in ONE pass (inserted text is never re-scanned for placeholders)."""
    unknown = sorted(set(re.findall(r"<<([A-Z_]+)>>", template)) - set(values))
    if unknown:
        raise TemplateError(f"No value supplied for placeholder(s): {unknown}")
    return re.sub(r"<<([A-Z_]+)>>", lambda m: values[m.group(1)], template)


# --------------------------------------------------------------------------
# LaTeX building blocks produced by code (never by the LLM)
# --------------------------------------------------------------------------
def placeholder_latex(text: str) -> str:
    return r"\textbf{[" + latex_escape(text) + "]}"


def build_authors(authors: List[Author]) -> str:
    if not authors:
        return placeholder_latex("AUTHORS MISSING")
    parts = []
    for a in authors:
        part = latex_escape(a.name)
        if a.affiliation:
            part += r"\\ {\small " + latex_escape(a.affiliation) + "}"
        parts.append(part)
    return "\n\\and\n".join(parts)


def build_draft_notice(is_simulated: bool) -> str:
    text = ("DRAFT: generated from supplied results by an AI-assisted tool. "
            "Check every claim, number and reference before any use.")
    if is_simulated:
        text += " SIMULATED SAMPLE DATA: the numbers and experiment are illustrative, not real results."
    return "\\begin{center}\n\\small\\textbf{" + latex_escape(text) + "}\n\\end{center}"


def build_results_table(rows: List[ResultRow], is_simulated: bool = False) -> str:
    if not rows:
        return placeholder_latex("RESULTS NOT PROVIDED")
    has_std = any(r.std is not None for r in rows)
    has_n = any(r.n is not None for r in rows)
    has_p = any(r.p_value is not None for r in rows)
    has_cmp = any(r.comparison for r in rows)
    header = ["Method", "Metric", "Value"] + (["Std"] if has_std else []) + (["$n$"] if has_n else []) \
        + (["$p$"] if has_p else []) + (["vs."] if has_cmp else [])
    align = "ll" + "r" * (len(header) - 2 - (1 if has_cmp else 0)) + ("l" if has_cmp else "")
    lines = []
    for r in rows:
        cells = [latex_escape(r.method), latex_escape(r.metric), fmt_number(r.value)]
        if has_std:
            cells.append(fmt_number(r.std) if r.std is not None else "--")
        if has_n:
            cells.append(str(r.n) if r.n is not None else "--")
        if has_p:
            cells.append(("$" + fmt_p(r.p_value) + "$") if r.p_value is not None else "--")
        if has_cmp:
            cells.append(latex_escape(r.comparison) if r.comparison else "--")
        lines.append(" & ".join(cells) + r" \\")
    caption = "Verified experimental results."
    if is_simulated:
        caption += " SIMULATED SAMPLE DATA, not real experiments."
    return ("\\begin{table}[t]\n\\centering\n\\caption{" + latex_escape(caption) + "}\n\\label{tab:results}\n"
            "\\resizebox{\\columnwidth}{!}{%\n\\begin{tabular}{" + align + "}\n\\toprule\n"
            + " & ".join(header) + " \\\\\n\\midrule\n" + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}%\n}\n"
            "\\end{table}")


def prepare_figures(figures: List[FigureInput], output_dir: Path) -> Tuple[str, List[str], List[str]]:
    """Copy figure files next to the .tex and return (latex, labels, copied relative paths)."""
    if not figures:
        return placeholder_latex("NO FIGURES PROVIDED"), [], []
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    blocks, labels, copied = [], [], []
    for i, fig in enumerate(figures, 1):
        src = Path(fig.path)
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", src.stem)[:30] or "figure"
        dest = fig_dir / f"fig{i}_{stem}{src.suffix.lower()}"
        try:
            if not (dest.exists() and dest.resolve() == src.resolve()):
                shutil.copy2(src, dest)
        except OSError as exc:
            raise SynthesizerError(f"Could not copy figure {src}: {exc}") from exc
        label = re.sub(r"[^A-Za-z0-9:_-]", "_", fig.label) if fig.label else f"fig:{i}"
        if not label.startswith("fig:"):
            label = "fig:" + label
        caption = latex_escape(fig.caption) if fig.caption else r"\textbf{[CAPTION MISSING]}"
        blocks.append("\\begin{figure}[t]\n\\centering\n\\includegraphics[width=\\columnwidth]{figures/"
                      + dest.name + "}\n\\caption{" + caption + "}\n\\label{" + label + "}\n\\end{figure}")
        labels.append(label)
        copied.append(f"figures/{dest.name}")
    return "\n\n".join(blocks), labels, copied


# --------------------------------------------------------------------------
# Checking and rendering LLM prose
# --------------------------------------------------------------------------
_CITE = re.compile(r"\\cite[tp]?\{([^{}]*)\}")
_REF = re.compile(r"\\ref\{([^{}]*)\}")
_MISSING = re.compile(r"\[MISSING:[^\]]*\]")
_TOKEN = re.compile(r"(\\cite[tp]?\{[^{}]*\}|\\ref\{[^{}]*\}|\[MISSING:[^\]]*\])")
_CLAIM_WORDS = re.compile(r"\b(novel|state[- ]of[- ]the[- ]art|first to|groundbreaking|unprecedented|outperforms all)\b", re.I)


@dataclass
class _Context:
    valid_keys: Set[str]
    valid_labels: Set[str]
    allowed_numbers: Set[float]
    has_significant_p: bool
    warnings: List[str] = field(default_factory=list)
    cited: List[str] = field(default_factory=list)


def check_and_render(raw: Any, ctx: _Context, section: str = "section") -> Tuple[Optional[str], List[str]]:
    """Validate an LLM answer. Returns (latex, []) if acceptable, else (None, problems)."""
    if not isinstance(raw, str) or not raw.strip():
        return None, ["the answer was empty"]
    text = re.sub(r"^```[A-Za-z]*\s*|\s*```\s*$", "", raw.strip()).strip()
    text = re.sub(r"\b(Table|Figure|Fig\.?)~(?=\\ref\{)", r"\1 ", text)  # "Table~\ref" typed by the model
    if text.startswith(("{", "[{")) and text.endswith(("}", "]")):
        return None, ["the answer is JSON; plain text paragraphs were required"]
    if re.search(r"^\s*#{1,6}\s", text, re.M):
        return None, ["the answer contains Markdown headings; headings are added by the template"]
    stripped = _CITE.sub(" ", _REF.sub(" ", _MISSING.sub(" ", text)))
    if len(text) < 40 and "[MISSING:" not in text:
        return None, ["the answer is too short to be a section"]
    problems: List[str] = []
    if re.search(r"\\[A-Za-z]+", stripped):
        problems.append("it uses LaTeX commands other than \\cite and \\ref")
    keys = [k.strip() for group in _CITE.findall(text) for k in group.split(",") if k.strip()]
    bad_keys = sorted({k for k in keys if k not in ctx.valid_keys})
    if bad_keys:
        problems.append(f"it cites unknown keys {bad_keys} (allowed: {sorted(ctx.valid_keys) or 'none'})")
    bad_labels = sorted({lab for lab in _REF.findall(text) if lab not in ctx.valid_labels})
    if bad_labels:
        problems.append(f"it references unknown labels {bad_labels} (allowed: {sorted(ctx.valid_labels) or 'none'})")
    bad_numbers = find_unverified_numbers(stripped, ctx.allowed_numbers)
    if bad_numbers:
        problems.append(f"it contains numbers that are not in the supplied data: {sorted(set(bad_numbers))}")
    if problems:
        return None, problems

    def render(part: str) -> str:
        if _CITE.fullmatch(part):
            return "\\cite{" + ",".join(k.strip() for k in _CITE.fullmatch(part).group(1).split(",")) + "}"
        if _REF.fullmatch(part):
            return "\\ref{" + _REF.fullmatch(part).group(1).strip() + "}"
        if _MISSING.fullmatch(part):
            return placeholder_latex(part[1:-1])
        return latex_escape(part)

    ctx.cited.extend(k for k in keys if k not in ctx.cited)
    for word in sorted({m.group(1).lower() for m in _CLAIM_WORDS.finditer(text)}):
        ctx.warnings.append(f"Section '{section}' uses the claim wording '{word}', which the supplied data does not verify; check it.")
    if re.search(r"significan", text, re.I) and not ctx.has_significant_p:
        ctx.warnings.append(f"Section '{section}' mentions significance but no supplied p-value is below 0.05; check it.")
    if "[MISSING:" in text:
        ctx.warnings.append(f"Section '{section}' contains [MISSING: ...] markers; supply that information.")
    pieces: List[str] = []
    for part in _TOKEN.split(text):
        rendered = render(part)
        if _REF.fullmatch(part):  # add the word "Table"/"Figure" unless the model already wrote it
            already = re.search(r"(table|figure|fig\.?)(\s|~)*$", "".join(pieces)[-12:], re.I)
            if not already:
                rendered = ("Table~" if _REF.fullmatch(part).group(1).startswith("tab:") else "Figure~") + rendered
        pieces.append(rendered)
    return "".join(pieces), []


_GUIDANCE = {
    "abstract": "Write a concise abstract (about 120-180 words): the question, the setup, and the verified results.",
    "introduction": "Write a short introduction (about 150-250 words): motivation from the hypothesis, related work "
                    "acknowledged with \\cite (by title only, unless an abstract is given), and the aim of the study.",
    "experimental_setup": "Describe the experimental setup (about 120-200 words) using ONLY the SETUP text.",
    "results_discussion": "Describe what the results table shows (about 100-200 words). Refer to the table with "
                          "\\ref{tab:results}. Report numbers only as listed in RESULTS.",
    "conclusion": "Write a short conclusion (about 80-150 words): restate the verified findings, mention the "
                  "LIMITATIONS, and suggest cautious next steps. Introduce no new numbers.",
}
_RULES = (
    "RULES (strict):\n"
    "1. Use ONLY the FACTS below. Never invent results, numbers, p-values, datasets, methods, citations or references.\n"
    "2. Every number you write must appear in FACTS (rounding is fine). Do not compute new numbers, differences or "
    "percentages. Write other small counts as words.\n"
    "3. Cite only with \\cite{key} using the listed keys. A cited paper may only be acknowledged as related work "
    "(or described by its abstract, if one is given). Do not describe its findings otherwise.\n"
    "4. Refer to tables and figures only with \\ref{label} using the listed labels. The word Table or Figure is added "
    "automatically, so write e.g. 'see \\ref{tab:results}'. Do not type table or figure numbers.\n"
    "5. If FACTS lack what is needed, write [MISSING: what is missing] instead of guessing.\n"
    "6. Do not claim novelty, state-of-the-art performance or statistical significance unless FACTS support it.\n"
    "7. Plain text paragraphs only. No LaTeX commands except \\cite and \\ref. No Markdown, headings, lists or JSON."
)


# --------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------
class SynthesizerAgent:
    """Generate a LaTeX paper draft and references.bib from verified results."""

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        template_path: Optional[Union[str, Path]] = None,
        max_retries: int = 1,
        use_env_llm: bool = True,
    ) -> None:
        if llm is None and use_env_llm and llm_client_from_env is not None:
            llm = llm_client_from_env()
        self.llm = llm
        self.template_path = Path(template_path) if template_path else DEFAULT_TEMPLATE
        self.max_retries = max(0, max_retries)

    # -- public helpers ----------------------------------------------------
    @staticmethod
    def validate_input(data: Union[PaperInput, Dict[str, Any]]) -> PaperInput:
        """Validate research data; raises InputValidationError."""
        return validate_paper_input(data)

    @staticmethod
    def build_bibtex(papers: List[PaperMeta]) -> BibResult:
        """Create references.bib content from paper metadata."""
        return build_bibtex(papers)

    # -- main entry point ----------------------------------------------------
    def synthesize(
        self,
        data: Union[PaperInput, Dict[str, Any]],
        output_dir: Union[str, Path] = "output",
        basename: str = "generated_research_paper",
        require_llm: bool = True,
    ) -> SynthesisResult:
        """Write ``<basename>.tex`` and ``references.bib`` into ``output_dir``.

        With ``require_llm=False`` and no LLM, prose sections become placeholders while the table,
        figures and bibliography are still built.
        """
        paper = validate_paper_input(data)
        if self.llm is None and require_llm:
            raise SynthesizerConfigError(
                "No LLM configured. Set LLM_PROVIDER, LLM_API_KEY and LLM_MODEL (see .env.example), "
                "pass llm=..., or call synthesize(..., require_llm=False) for a placeholder-only draft.")
        template = load_template(self.template_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        bib = build_bibtex(paper.papers)
        figures_tex, fig_labels, fig_files = prepare_figures(paper.figures, out)
        labels = set(fig_labels) | ({"tab:results"} if paper.results else set())
        facts = self._facts(paper, bib, fig_labels)
        ctx = _Context(
            valid_keys=set(bib.keys.values()), valid_labels=labels, allowed_numbers=build_allowed_numbers(facts),
            has_significant_p=any(r.p_value is not None and r.p_value < 0.05 for r in paper.results))

        sections: Dict[str, str] = {}
        tex_parts: Dict[str, str] = {}
        for name in SECTIONS:
            skip = self._skip_reason(name, paper)
            if skip:
                tex_parts[name], sections[name] = placeholder_latex(f"{name.upper().replace('_', ' ')} NOT GENERATED: {skip}"), f"placeholder: {skip}"
            elif self.llm is None:
                reason = "no LLM configured"
                tex_parts[name], sections[name] = placeholder_latex(f"{name.upper().replace('_', ' ')} NOT GENERATED: {reason}"), f"placeholder: {reason}"
            else:
                tex_parts[name], sections[name] = self._write_section(name, facts, ctx)

        if ctx.cited:
            bibliography = f"\\bibliographystyle{{ieeetr}}\n\\bibliography{{references}}"
        elif paper.papers:
            bibliography = "\\section*{References}\n" + placeholder_latex("NO REFERENCES CITED")
        else:
            bibliography = "\\section*{References}\n" + placeholder_latex("NO REFERENCES PROVIDED")

        tex = render_template(template, {
            "TITLE": latex_escape(paper.title), "AUTHORS": build_authors(paper.authors),
            "DRAFT_NOTICE": build_draft_notice(paper.is_simulated), "ABSTRACT": tex_parts["abstract"],
            "INTRODUCTION": tex_parts["introduction"], "EXPERIMENTAL_SETUP": tex_parts["experimental_setup"],
            "RESULTS_TABLE": build_results_table(paper.results, paper.is_simulated),
            "RESULTS_DISCUSSION": tex_parts["results_discussion"], "FIGURES": figures_tex,
            "CONCLUSION": tex_parts["conclusion"], "BIBLIOGRAPHY": bibliography})

        tex_path, bib_path = out / f"{basename}.tex", out / "references.bib"
        tex_path.write_text(tex, encoding="utf-8")
        bib_path.write_text(bib.text, encoding="utf-8")

        generated = sum(1 for s in sections.values() if s == "llm")
        status = "complete" if generated == len(SECTIONS) else ("partial" if generated else "placeholders_only")
        warnings = bib.warnings + ctx.warnings
        for name, state in sections.items():
            if state != "llm":
                warnings.append(f"Section '{name}' is a placeholder ({state.removeprefix('placeholder: ')}).")
        logger.info("Synthesis %s: %s (%d/%d sections from the LLM)", status, tex_path, generated, len(SECTIONS))
        return SynthesisResult(
            status=status, tex_path=str(tex_path), bib_path=str(bib_path), sections=sections,
            cited_keys=ctx.cited, bib_keys=bib.keys, figures=fig_files, warnings=warnings,
            is_simulated=paper.is_simulated)

    # -- internals ------------------------------------------------------------
    @staticmethod
    def _skip_reason(name: str, paper: PaperInput) -> Optional[str]:
        if name == "experimental_setup" and not (paper.experimental_setup or "").strip():
            return "no experimental setup was provided"
        if name == "results_discussion" and not paper.results:
            return "no verified results were provided"
        return None

    @staticmethod
    def _facts(paper: PaperInput, bib: BibResult, fig_labels: List[str]) -> str:
        lines = [f"TITLE: {paper.title}", f"HYPOTHESIS: {paper.hypothesis or '(not provided)'}",
                 f"SETUP: {paper.experimental_setup or '(not provided)'}"]
        if paper.results:
            lines.append("RESULTS (verified; the only numbers you may use):")
            for r in paper.results:
                extra = (f", std {fmt_number(r.std)}" if r.std is not None else "") + (f", n={r.n}" if r.n else "") \
                    + (f", p{fmt_p(r.p_value) if r.p_value < 0.001 else '=' + fmt_p(r.p_value)}" if r.p_value is not None else "") \
                    + (f" (compared with {r.comparison})" if r.comparison else "")
                lines.append(f"- {r.method} | {r.metric} = {fmt_number(r.value)}{extra}")
        else:
            lines.append("RESULTS: (none provided)")
        lines.append("LIMITATIONS: " + ("; ".join(paper.limitations) if paper.limitations else "(none provided)"))
        labels = (["tab:results (results table)"] if paper.results else []) + [
            f"{lab} ({(f.caption or 'no caption')})" for lab, f in zip(fig_labels, paper.figures)]
        lines.append("LABELS you may \\ref: " + (", ".join(labels) if labels else "(none)"))
        by_id = {p.paper_id: p for p in paper.papers}
        cite_lines = []
        for pid, key in bib.keys.items():
            p = by_id[pid]
            who = (p.authors[0] + (" et al." if len(p.authors) > 1 else "")) if p.authors else "unknown authors"
            entry = f"- {key}: \"{p.title}\" ({who}, {p.year or 'n.d.'})"
            if p.abstract:
                entry += f" ABSTRACT: {p.abstract[:600]}"
            cite_lines.append(entry)
        lines.append("CITATION KEYS you may \\cite:\n" + ("\n".join(cite_lines) if cite_lines else "(none: do not cite anything)"))
        if paper.is_simulated:
            lines.append("DATA STATUS: SIMULATED SAMPLE DATA. State clearly that the results are simulated and illustrative.")
        return "\n".join(lines)

    def _write_section(self, name: str, facts: str, ctx: _Context) -> Tuple[str, str]:
        prompt = (f"You are writing the \"{name.replace('_', ' ')}\" section of a research paper draft.\n"
                  f"SECTION: {name}\n{_GUIDANCE[name]}\n\n{_RULES}\n\nFACTS:\n{facts}\n")
        feedback = ""
        last_problem = "unknown problem"
        for attempt in range(self.max_retries + 1):
            try:
                raw = self.llm.complete(prompt + feedback)  # type: ignore[union-attr]
            except LLMError as exc:
                last_problem = f"LLM error: {exc}"
                logger.warning("Section %s attempt %d failed: %s", name, attempt + 1, last_problem)
                continue
            except Exception as exc:  # any provider failure becomes a placeholder, never a crash
                last_problem = f"LLM call failed: {type(exc).__name__}: {exc}"
                logger.warning("Section %s attempt %d failed: %s", name, attempt + 1, last_problem)
                continue
            latex, problems = check_and_render(raw, ctx, name)
            if latex is not None:
                return latex, "llm"
            last_problem = "; ".join(problems)
            logger.warning("Section %s attempt %d rejected: %s", name, attempt + 1, last_problem)
            feedback = ("\n\nYour previous answer was REJECTED because: " + last_problem
                        + ". Rewrite the section and fix every problem.")
        short = last_problem if len(last_problem) <= 180 else last_problem[:177] + "..."
        # The reason (which may quote rejected, invented numbers) goes to the warnings only,
        # never into the paper text.
        return (placeholder_latex(f"{name.upper().replace('_', ' ')} NOT GENERATED: the model text failed the "
                                  "automatic checks; write this section manually"), f"placeholder: {short}")
