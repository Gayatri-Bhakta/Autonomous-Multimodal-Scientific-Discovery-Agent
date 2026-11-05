"""Generate a research paper draft (LaTeX + BibTeX + PDF) with the Synthesizer Agent.

Run from the project root (PowerShell)::

    python examples/run_paper_synthesis.py                    # sample data, LLM from .env
    python examples/run_paper_synthesis.py --no-llm           # placeholder-only draft, no API needed
    python examples/run_paper_synthesis.py --input my_results.json

The built-in sample is SIMULATED: the numbers and the experiment are illustrative, not real
results. Only the three cited papers are real. The paper text is written by the configured LLM
(LLM_PROVIDER / LLM_API_KEY / LLM_MODEL); sections the LLM cannot write safely become placeholders.

Outputs (in ./output by default): generated_research_paper.tex, references.bib,
generated_research_paper.pdf (only if pdflatex works), and an HTML/Markdown fallback otherwise.
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # optional: pick up a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from src.agents.synthesizer_agent import (  # noqa: E402
    InputValidationError,
    SynthesizerAgent,
    SynthesizerConfigError,
    SynthesizerError,
)
from src.utils.latex_compiler import compile_with_fallback  # noqa: E402

SAMPLE_RESULTS = {
    "title": "Residual and Attention Architectures on a Synthetic Classification Task (Simulated Study)",
    "authors": [{"name": "A. Researcher", "affiliation": "Example Institute"}],
    "hypothesis": ("Residual connections and attention layers improve classification accuracy over a plain "
                   "feed-forward baseline."),
    "experimental_setup": (
        "SIMULATED EXPERIMENT. Task: synthetic tabular classification. Models: a plain feed-forward "
        "baseline (MLP), a residual-style network, and an attention-based encoder. All models are trained "
        "with the Adam optimizer. Each model is trained with 10 random seeds and evaluated on a held-out split."),
    "results": [
        {"method": "MLP baseline", "metric": "accuracy", "value": 0.8123, "std": 0.0210, "n": 10},
        {"method": "Residual network", "metric": "accuracy", "value": 0.8467, "std": 0.0185, "n": 10,
         "p_value": 0.0031, "comparison": "MLP baseline"},
        {"method": "Attention encoder", "metric": "accuracy", "value": 0.8589, "std": 0.0172, "n": 10,
         "p_value": 0.0008, "comparison": "MLP baseline"},
    ],
    "limitations": ["All data are synthetic and simulated.", "Only one task and one metric were used."],
    "papers": [
        {"paper_id": "arxiv:1706.03762", "title": "Attention Is All You Need", "year": 2017,
         "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit", "Llion Jones",
                     "Aidan N. Gomez", "Lukasz Kaiser", "Illia Polosukhin"],
         "url": "https://arxiv.org/abs/1706.03762"},
        {"paper_id": "arxiv:1412.6980", "title": "Adam: A Method for Stochastic Optimization", "year": 2014,
         "authors": ["Diederik P. Kingma", "Jimmy Ba"], "url": "https://arxiv.org/abs/1412.6980"},
        {"paper_id": "arxiv:1512.03385", "title": "Deep Residual Learning for Image Recognition", "year": 2015,
         "authors": ["Kaiming He", "Xiangyu Zhang", "Shaoqing Ren", "Jian Sun"],
         "url": "https://arxiv.org/abs/1512.03385"},
    ],
    "is_simulated": True,
}


def make_sample_figure(results, path):
    """Bar chart of the sample accuracies (needs matplotlib; returns False if unavailable)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(4, 2.6))
    ax.bar([r["method"] for r in results], [r["value"] for r in results],
           yerr=[r.get("std", 0) for r in results], capsize=3, color="#4477aa")
    ax.set_ylabel("Accuracy (simulated)")
    ax.set_ylim(0.7, 0.9)
    plt.xticks(rotation=15, ha="right", fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return True


def main(argv=None, llm=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=None, help="JSON file with verified results (see SAMPLE_RESULTS)")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--no-llm", action="store_true", help="placeholder-only draft (no API call)")
    parser.add_argument("--skip-pdf", action="store_true", help="write .tex/.bib only")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.input:
        with open(args.input, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.loads(json.dumps(SAMPLE_RESULTS))
        figure = os.path.join(args.output_dir, "sample_inputs", "accuracy_by_model.png")
        if make_sample_figure(data["results"], figure):
            data["figures"] = [{"path": figure, "label": "accuracy",
                                "caption": "Simulated accuracy of the three models (mean and standard deviation)."}]
        else:
            print("Note: matplotlib is not installed, so the sample has no figure (placeholder used).")

    agent = SynthesizerAgent(llm=llm, use_env_llm=not args.no_llm)
    try:
        result = agent.synthesize(data, output_dir=args.output_dir, require_llm=not args.no_llm)
    except InputValidationError as exc:
        print("INPUT ERROR:\n  - " + "\n  - ".join(exc.problems))
        return 1
    except SynthesizerConfigError as exc:
        print(f"CONFIG ERROR: {exc}")
        return 1
    except SynthesizerError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"\nSynthesis status: {result.status}")
    for name, state in result.sections.items():
        print(f"  {name}: {state}")
    print(f"LaTeX : {result.tex_path}\nBibTeX: {result.bib_path}")
    for warning in result.warnings:
        print(f"  warning: {warning}")

    report = {"synthesis": result.model_dump()}
    if not args.skip_pdf:
        compiled = compile_with_fallback(result.tex_path, result.bib_path)
        report["compile"] = compiled.model_dump()
        if compiled.pdf_ok:
            print(f"PDF   : {compiled.pdf_path}")
        else:
            print(f"PDF   : NOT generated. {compiled.message}")
            for err in compiled.errors:
                print(f"  latex error: {err}")
            for path in compiled.fallback_files:
                print(f"Fallback: {path}")
    with open(os.path.join(args.output_dir, "synthesis_report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
