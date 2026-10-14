"""
Hypothesis Generator Agent
Core Multi-Agent Discovery Triad

Formulates novel, falsifiable scientific hypotheses grounded in literature synthesis
and research bottlenecks. Ranks hypotheses and selects the top candidate for code execution.
The orchestrator calls generate_hypothesis(literature_summary).
"""

from __future__ import annotations

from typing import List, Tuple


CANDIDATE_TEMPLATES = [
    (
        "Dynamic token-level pruning reduces inference memory footprint by 30% with <1% perplexity loss.",
        0.92,
        "Memory efficiency & latency reduction in large transformer architectures."
    ),
    (
        "Iterative reinforcement learning self-debugging loops increase task success rates by >18% over static prompting.",
        0.88,
        "Code execution robustness & autonomous error correction."
    ),
    (
        "Cross-modal embedding alignment improves zero-shot scientific graph reasoning precision by 12%.",
        0.85,
        "Multimodal scientific data comprehension across charts and abstracts."
    ),
]


def extract_key_concepts(literature_summary: str) -> List[str]:
    """Identify focal keywords from literature review."""
    potential = ["reasoning", "pruning", "memory", "reinforcement", "multimodal", "sandbox", "agent"]
    text_lower = literature_summary.lower()
    found = [word for word in potential if word in text_lower]
    return found if found else ["reasoning", "pruning"]


def generate_candidate_hypotheses(literature_summary: str) -> List[Tuple[str, float, str]]:
    """
    Generate prioritized list of hypotheses with estimated novelty and domain rationale.
    In future iterations, this connects to LLM inference with structured JSON output.
    """
    concepts = extract_key_concepts(literature_summary)

    # Return candidates ranked by score
    return sorted(CANDIDATE_TEMPLATES, key=lambda x: x[1], reverse=True)


def generate_hypothesis(literature_summary: str) -> str:
    """
    Main entry point invoked by the Multi-Agent Orchestrator.
    Returns the top-ranked falsifiable hypothesis string.
    """
    candidates = generate_candidate_hypotheses(literature_summary)
    top_hypothesis, score, rationale = candidates[0]
    return f"Hypothesis: {top_hypothesis}"


def generate_all_hypotheses(literature_summary: str) -> List[str]:
    """Returns all formatted candidate hypotheses."""
    candidates = generate_candidate_hypotheses(literature_summary)
    return [f"Hypothesis ({score:.2f} confidence): {hyp}" for hyp, score, _ in candidates]


if __name__ == "__main__":
    sample_summary = "Bottlenecks identified in memory footprint and latency during agent reasoning."
    print("Top hypothesis:", generate_hypothesis(sample_summary))
    print("All candidates:", generate_all_hypotheses(sample_summary))
