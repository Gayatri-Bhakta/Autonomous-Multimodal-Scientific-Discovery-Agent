import streamlit as st

from src.frontend import components as ui
from src.frontend.services.status import module_status

ui.page_header("About Project", "Autonomous Multimodal Scientific Discovery Agent")
st.markdown("""
A self-directed, multimodal AI research assistant: it ingests recent preprints, formulates hypotheses grounded in the
retrieved evidence, reads charts with a vision-language model, runs experiments in a sandbox and synthesises results
into a formatted research draft.

**Modules**
- Week 1 - Literature reviewer, ingestion (arXiv / PubMed) and vector store
- Week 2 - Evidence-grounded hypothesis generator with citation validation
- Week 3 - Vision-language chart reader (structured JSON)
- Week 4 - LaTeX synthesis engine and PDF compiler
- Code executor - sandboxed experiment runner

**Honesty rules built into the app**
- No AI output is simulated: pages show backend results or a clear error.
- Hypotheses are proposals; novelty is not verified.
- Chart values are labelled observed / estimated / uncertain.
- Paper numbers come from data you supply; the LLM cannot add numbers or citations.
- API keys are read from the environment and never displayed.
""")
st.subheader("Current connection status")
st.dataframe([{k: m[k] for k in ("week", "name", "state", "detail")} for m in module_status()], width="stretch", hide_index=True)
