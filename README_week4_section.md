## LaTeX Synthesis Engine (Week 4)

Turns **verified** experimental results into a LaTeX research-paper draft, a `references.bib` file and (when LaTeX is installed) a PDF.

- `templates/paper_template.tex` - two-column conference-style template with `<<PLACEHOLDERS>>`.
- `src/agents/synthesizer_agent.py` - `SynthesizerAgent`. The LLM writes only the prose sections. Numbers, p-values, the results table, figures and BibTeX are produced by code from your data. LLM text is rejected (retried once, then replaced by a visible placeholder) if it cites an unknown reference, uses a number that is not in your data, or contains LaTeX commands.
- `src/utils/latex_compiler.py` - runs `pdflatex` (+ `bibtex`). If LaTeX is missing or fails, it says so (no PDF is claimed) and writes an HTML (MathJax) + Markdown fallback.

### Configure the LLM
Same variables as the Hypothesis agent, in `.env` (never commit it):
```
LLM_PROVIDER=anthropic        # or openai
LLM_API_KEY=your_key_here
LLM_MODEL=your_model_name
```

### Run the example (PowerShell, from the project root)
```powershell
python examples/run_paper_synthesis.py            # uses the LLM from .env
python examples/run_paper_synthesis.py --no-llm   # placeholder-only draft, no API call
python examples/run_paper_synthesis.py --input my_results.json
```
The built-in sample data is **simulated** (the numbers are illustrative, not real results); the paper says so in its draft notice.

### Install / check LaTeX
```powershell
pdflatex --version
```
If that fails, install MiKTeX (https://miktex.org/download) or TeX Live, then restart the terminal. MiKTeX may ask to install missing packages on first run; allow it.

### Output (folder `output/`)
`generated_research_paper.tex`, `references.bib`, `generated_research_paper.pdf` (only if compilation worked), `figures/`, `synthesis_report.json`. Without LaTeX you get `generated_research_paper.html` and `.md` instead.

### Tests
```powershell
python -m pytest tests/test_synthesizer_agent.py tests/test_latex_compiler.py -v
```
