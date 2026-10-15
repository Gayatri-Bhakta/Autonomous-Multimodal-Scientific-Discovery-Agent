"""HypothesisGenerator agent.

Turns a literature review (the JSON produced by ``LiteratureReviewer``) into
testable, AI-generated hypotheses with variables, metrics, methods and a
validation plan.

This module is independent: it does NOT import the other agents. It accepts a
plain ``dict`` (or JSON file) with the keys ``topic``, ``papers`` and
``analysis`` (``themes`` / ``limitations`` / ``research_gaps``).

Honesty rules enforced in code:

* ``evidence_based_observations`` (copied from the input) are kept separate
  from ``ai_generated_hypotheses``.
* Every hypothesis is tagged ``origin="ai_generated"`` and
  ``novelty_status="not_verified"``. Novelty is never claimed.
* Dataset names are *suggestions* that a human must verify.

External services / credentials: optional LLM provider via LLM_PROVIDER,
LLM_API_KEY, LLM_MODEL (and optional LLM_BASE_URL). Without them the
template-based fallback runs offline.

Run from the project root::

    python -m agents.hypothesis_generator            # built-in sample input
    python -m agents.hypothesis_generator review.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Hypotheses below are AI-generated proposals, not findings. Novelty has NOT "
    "been verified; a human must search the literature and review each "
    "hypothesis before running experiments. Suggested datasets are unverified "
    "suggestions."
)


# --------------------------------------------------------------------------
# LLM provider interface (configurable)
# --------------------------------------------------------------------------
class LLMError(RuntimeError):
    """Raised when the LLM provider call fails."""


class LLMClient(Protocol):
    """Anything with ``complete(prompt) -> str`` can act as an LLM provider."""

    def complete(self, prompt: str) -> str:  # pragma: no cover - protocol
        ...


class HTTPLLMClient:
    """Standard-library LLM client for Anthropic or OpenAI-compatible APIs."""

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: str,
        base_url: Optional[str] = None,
        timeout: float = 90.0,
        max_tokens: int = 4000,
    ) -> None:
        self.provider = provider.lower()
        self._api_key = api_key  # never logged
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        """Send ``prompt`` and return the reply text."""
        if self.provider == "anthropic":
            url = (self.base_url or "https://api.anthropic.com") + "/v1/messages"
            headers = {
                "content-type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            }
            payload: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
        elif self.provider == "openai":
            url = (self.base_url or "https://api.openai.com/v1") + "/chat/completions"
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self._api_key}",
            }
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
        else:
            raise LLMError(f"Unsupported LLM_PROVIDER: {self.provider!r}")

        request = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if self.provider == "anthropic":
                return "".join(
                    b.get("text", "") for b in data["content"] if b.get("type") == "text"
                )
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc


def llm_client_from_env() -> Optional[HTTPLLMClient]:
    """Build an LLM client from environment variables, or ``None``."""
    api_key, model = os.getenv("LLM_API_KEY"), os.getenv("LLM_MODEL")
    if not api_key or not model:
        return None
    return HTTPLLMClient(
        provider=os.getenv("LLM_PROVIDER", "anthropic"),
        api_key=api_key,
        model=model,
        base_url=os.getenv("LLM_BASE_URL") or None,
    )


def _extract_json(text: str) -> Any:
    """Parse the first JSON object found in ``text``."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output.")
    return json.loads(text[start : end + 1])


# --------------------------------------------------------------------------
# Data models
# --------------------------------------------------------------------------
class Observation(BaseModel):
    """An evidence-based observation taken from the supplied literature review."""

    kind: str  # "theme" | "limitation" | "research_gap"
    text: str
    source_ids: List[str] = Field(default_factory=list)
    label: str = "evidence_based"


class Hypothesis(BaseModel):
    """One AI-generated, testable hypothesis."""

    hypothesis_id: str
    statement: str
    motivation: str
    based_on_gap: str
    evidence_source_ids: List[str] = Field(default_factory=list)
    independent_variables: List[str]
    dependent_variables: List[str]
    suggested_datasets: List[str]
    evaluation_metrics: List[str]
    experiment_methods: List[str]
    validation_plan: List[str]
    origin: str = "ai_generated"
    novelty_status: str = "not_verified"


class HypothesisReport(BaseModel):
    """JSON-compatible output of ``HypothesisGenerator.generate``."""

    status: str  # "ok" | "insufficient_evidence"
    topic: str
    mode: str  # "fallback" | "llm"
    generated_at: str
    evidence_based_observations: List[Observation] = Field(default_factory=list)
    ai_generated_hypotheses: List[Hypothesis] = Field(default_factory=list)
    notes: str = ""
    disclaimer: str = DISCLAIMER


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _as_findings(items: Any, kind: str) -> List[Observation]:
    """Normalise review items (dicts or plain strings) into Observations."""
    out: List[Observation] = []
    for item in items or []:
        if isinstance(item, str):
            out.append(Observation(kind=kind, text=item))
        elif isinstance(item, dict) and item.get("text"):
            out.append(
                Observation(
                    kind=kind,
                    text=str(item["text"]),
                    source_ids=[str(i) for i in item.get("source_ids", [])],
                )
            )
    return out


# Generic datasets that ship with scikit-learn / can be generated offline,
# which matches the network-free sandbox used by CodeExecutor.
_PROXY_DATASETS = [
    "scikit-learn built-in: load_breast_cancer (verify relevance to the topic)",
    "scikit-learn built-in: load_wine (verify relevance to the topic)",
    "synthetic data from sklearn.datasets.make_classification (controllable noise)",
]


# --------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------
class HypothesisGenerator:
    """Generate testable hypotheses from a literature review."""

    def __init__(
        self, llm: Optional[LLMClient] = None, max_hypotheses: int = 3
    ) -> None:
        self.llm = llm if llm is not None else llm_client_from_env()
        self.max_hypotheses = max(1, max_hypotheses)

    # -- public API ---------------------------------------------------------
    def generate(self, review: Dict[str, Any]) -> HypothesisReport:
        """Create a ``HypothesisReport`` from review results (a dict)."""
        topic = str(review.get("topic", "unknown topic"))
        analysis = review.get("analysis") or {}
        observations = (
            _as_findings(analysis.get("themes"), "theme")
            + _as_findings(analysis.get("limitations"), "limitation")
            + _as_findings(analysis.get("research_gaps"), "research_gap")
        )
        gaps = [o for o in observations if o.kind == "research_gap"] or [
            o for o in observations if o.kind == "limitation"
        ]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if not gaps:
            return HypothesisReport(
                status="insufficient_evidence",
                topic=topic,
                mode="fallback",
                generated_at=now,
                evidence_based_observations=observations,
                notes="No research gaps or limitations were supplied, so no "
                "hypotheses were generated.",
            )

        gaps = gaps[: self.max_hypotheses]
        known_ids = {str(p.get("arxiv_id")) for p in review.get("papers", [])}
        mode, notes = "fallback", "Template-based fallback (no LLM configured)."
        hypotheses: List[Hypothesis] = []

        if self.llm is not None:
            try:
                hypotheses = self._llm_hypotheses(topic, observations, gaps, known_ids)
                mode, notes = "llm", "Generated by an LLM from the supplied evidence."
            except (LLMError, ValueError, ValidationError, KeyError, TypeError) as exc:
                logger.warning("LLM generation failed (%s); using fallback.", exc)
                notes = f"LLM generation failed ({exc}); used template fallback."
        if not hypotheses:
            hypotheses = self._fallback_hypotheses(topic, gaps)

        return HypothesisReport(
            status="ok",
            topic=topic,
            mode=mode,
            generated_at=now,
            evidence_based_observations=observations,
            ai_generated_hypotheses=hypotheses,
            notes=notes,
        )

    def generate_from_file(self, path: str) -> HypothesisReport:
        """Load a JSON review file (saved by LiteratureReviewer) and generate."""
        with open(path, "r", encoding="utf-8") as handle:
            return self.generate(json.load(handle))

    # -- fallback -----------------------------------------------------------
    @staticmethod
    def _fallback_hypotheses(topic: str, gaps: List[Observation]) -> List[Hypothesis]:
        """Deterministic templates. Generic by design: a human should refine."""
        hypotheses = []
        for index, gap in enumerate(gaps, start=1):
            short_gap = gap.text if len(gap.text) <= 200 else gap.text[:197] + "..."
            hypotheses.append(
                Hypothesis(
                    hypothesis_id=f"H{index}",
                    statement=(
                        "A model variant designed to address the issue below achieves "
                        "a higher mean cross-validated macro-F1 than an otherwise "
                        "identical baseline on a controlled proxy task. "
                        f"Issue: {short_gap}"
                    ),
                    motivation=(
                        f"The literature review for '{topic}' reported the issue "
                        "above (see evidence_source_ids). The hypothesis turns it "
                        "into a measurable comparison."
                    ),
                    based_on_gap=gap.text,
                    evidence_source_ids=gap.source_ids,
                    independent_variables=[
                        "model variant (baseline vs. modified)",
                        "noise level or training-set size (factor related to the issue)",
                    ],
                    dependent_variables=["macro-F1", "accuracy"],
                    suggested_datasets=list(_PROXY_DATASETS),
                    evaluation_metrics=[
                        "macro-F1 (mean and std over seeds)",
                        "accuracy",
                        "paired Wilcoxon signed-rank test p-value",
                    ],
                    experiment_methods=[
                        "Controlled A/B comparison using scikit-learn pipelines",
                        "Repeated stratified k-fold cross-validation with fixed seeds",
                        "Ablation: remove the modification and re-measure",
                    ],
                    validation_plan=[
                        "Run at least 10 random seeds and report mean and std.",
                        "Compare against a baseline with identical preprocessing.",
                        "Apply a paired significance test and report effect size.",
                        "Repeat on a second dataset to check consistency.",
                        "Manually search the literature to check novelty before "
                        "making any novelty claim.",
                        "Human review of code and results before drafting a paper.",
                    ],
                )
            )
        return hypotheses

    # -- LLM path -----------------------------------------------------------
    def _llm_hypotheses(
        self,
        topic: str,
        observations: List[Observation],
        gaps: List[Observation],
        known_ids: set,
    ) -> List[Hypothesis]:
        assert self.llm is not None
        evidence = "\n".join(
            f"- ({o.kind}) {o.text} [sources: {', '.join(o.source_ids) or 'n/a'}]"
            for o in observations
        )
        prompt = (
            f"Topic: {topic}\n\nEvidence from a literature review:\n{evidence}\n\n"
            f"Propose up to {len(gaps)} testable hypotheses that address the gaps. "
            "Do not claim novelty. Do not invent papers or results. Prefer "
            "experiments runnable offline with NumPy/pandas/scikit-learn.\n\n"
            'Reply with JSON only: {"hypotheses":[{"statement":"...",'
            '"motivation":"...","based_on_gap":"...","evidence_source_ids":["id"],'
            '"independent_variables":["..."],"dependent_variables":["..."],'
            '"suggested_datasets":["..."],"evaluation_metrics":["..."],'
            '"experiment_methods":["..."],"validation_plan":["..."]}]}'
        )
        data = _extract_json(self.llm.complete(prompt))
        results: List[Hypothesis] = []
        for index, raw in enumerate(data["hypotheses"][: self.max_hypotheses], start=1):
            raw = dict(raw)
            raw["hypothesis_id"] = f"H{index}"
            raw["origin"] = "ai_generated"  # enforced, never trusted from the LLM
            raw["novelty_status"] = "not_verified"
            raw["evidence_source_ids"] = [
                i for i in raw.get("evidence_source_ids", []) if i in known_ids
            ]
            results.append(Hypothesis(**raw))
        if not results:
            raise ValueError("LLM returned no hypotheses")
        return results


# --------------------------------------------------------------------------
# Sample input / CLI
# --------------------------------------------------------------------------
SAMPLE_REVIEW: Dict[str, Any] = {
    "topic": "example topic",
    "papers": [{"arxiv_id": "EXAMPLE-ID-1", "title": "(placeholder, not a real paper)"}],
    "analysis": {
        "themes": [{"text": "example theme", "source_ids": ["EXAMPLE-ID-1"]}],
        "limitations": [],
        "research_gaps": [
            {
                "text": "Possible gap: models degrade when training data is noisy.",
                "source_ids": ["EXAMPLE-ID-1"],
            }
        ],
    },
}


def main() -> None:
    """Command-line entry point (run from the project root)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    generator = HypothesisGenerator()
    if len(sys.argv) > 1:
        report = generator.generate_from_file(sys.argv[1])
    else:
        report = generator.generate(SAMPLE_REVIEW)
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()



def generate_hypothesis(literature_summary: str) -> str:
    """Generate one hypothesis from a literature summary."""
    summary = (literature_summary or "").strip()

    if not summary:
        return "Insufficient evidence: literature summary is empty."

    generator = HypothesisGenerator()

    report = generator.generate({
        "topic": "Scientific Discovery",
        "analysis": {
            "research_gaps": [
                {
                    "text": summary[:200],
                    "source_ids": []
                }
            ]
        }
    })

    hypotheses = report.ai_generated_hypotheses

    if hypotheses:
        return f"Hypothesis: {hypotheses[0].statement}"

    return (
        "Insufficient evidence to generate a hypothesis. "
        "Please provide a research gap or limitation."
    )


def generate_all_hypotheses(literature_summary: str) -> list[str]:
    """Generate all hypotheses available from the supplied summary."""
    summary = (literature_summary or "").strip()

    if not summary:
        return []

    generator = HypothesisGenerator()

    report = generator.generate({
        "topic": "Scientific Discovery",
        "analysis": {
            "research_gaps": [
                {
                    "text": summary[:200],
                    "source_ids": []
                }
            ]
        }
    })

    return [
        f"Hypothesis: {hypothesis.statement}"
        for hypothesis in report.ai_generated_hypotheses
    ]
