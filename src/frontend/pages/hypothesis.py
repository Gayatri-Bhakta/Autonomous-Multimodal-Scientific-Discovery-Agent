import json

import streamlit as st

from src.frontend import components as ui
from src.frontend.services import hypothesis as hyp_service
from src.frontend.utils import state
from src.frontend.utils.env import llm_status
from src.frontend.utils.files import validate_upload

state.init_state()
ui.page_header("Hypothesis Generation", "Week 2: evidence-grounded, testable hypotheses with validated citations.")
llm = llm_status()

st.session_state["topic"] = st.text_input("Research topic", value=st.session_state["topic"],
                                          placeholder="e.g. graph neural networks for drug discovery")

st.subheader("1. Evidence (retrieved paper chunks)")
st.caption("JSON/JSONL list of chunks, each with a paper id (paper_id / arxiv_id / pmid) and text (text / abstract). "
           "At least 2 different papers are needed.")
upload = st.file_uploader("Upload evidence file", type=["json", "jsonl"], key="evidence_upload")
if upload is not None:
    data = upload.getvalue()
    error = validate_upload(upload.name, data, (".json", ".jsonl"), 10)
    if error:
        st.error(error)
    elif st.session_state["chunk_source"] != upload.name:
        res = hyp_service.parse_chunks(data, upload.name)
        if res.ok:
            st.session_state["chunks"], st.session_state["chunk_source"] = res.data, upload.name
            state.add_upload("evidence", upload.name, len(data))
            st.session_state["hypothesis_report"] = None
        ui.show_result(res)
chunks = st.session_state["chunks"]
if chunks:
    st.dataframe(hyp_service.summarize_chunks(chunks), width="stretch", hide_index=True)

st.subheader("2. Generate")
c1, c2 = st.columns(2)
max_h = c1.slider("Maximum hypotheses", 1, 5, 3)
strict = c2.checkbox("Require supporting findings to be exact quotes", value=True,
                     help="Rejects findings that are not found verbatim in the cited paper's text.")
if not llm["configured"]:
    st.warning("LLM not configured. Set LLM_API_KEY and LLM_MODEL (see .env.example), then restart the app.")
if st.button("Generate grounded hypotheses", type="primary", disabled=not (llm["configured"] and chunks)):
    with st.spinner("Asking the model and validating every hypothesis..."):
        res = hyp_service.generate(chunks, st.session_state["topic"], max_h, strict)
    st.session_state["hypothesis_report"] = res.data if res.data is not None else None
    state.add_trace("Hypothesis generation", "ok" if res.ok else "error", res.seconds, res.message, llm["model"] or "")
    ui.show_result(res)

report = st.session_state["hypothesis_report"]
if report is not None:
    st.subheader("3. Results")
    titles = {c.get("paper_id") or c.get("arxiv_id") or c.get("pmid"): c.get("title", "") for c in chunks}
    st.caption("The backend does not produce confidence scores, so none are shown. Hypotheses are AI-generated proposals; "
               "novelty is not verified.")
    for i, h in enumerate(report.hypotheses):
        with st.expander(f"H{i + 1}: {h.title}", expanded=(i == 0)):
            st.markdown(f"**Problem:** {h.problem_statement}")
            st.markdown(f"**Proposed solution:** {h.proposed_solution}")
            st.markdown(f"**Falsifiable metric:** {h.falsifiable_metric}")
            st.markdown("**Expected code modules:** " + ", ".join(f"`{m}`" for m in h.expected_code_modules))
            st.markdown("**Cited papers:** " + "; ".join(f"`{p}` {titles.get(p, '')}" for p in h.cited_paper_ids))
            st.markdown("**Supporting findings:**")
            for f in h.supporting_findings:
                st.markdown(f"- `{f.paper_id}`: \"{f.finding}\"")
            if st.button("Use this hypothesis in the paper", key=f"use_h{i}"):
                st.session_state["selected_hypothesis"] = h.model_dump(mode="json")
                st.success("Selected. Open Research Paper Generation.")
    if report.rejected:
        with st.expander(f"Rejected by validation ({len(report.rejected)})"):
            for r in report.rejected:
                st.json({"errors": r.errors, "title": r.raw.get("title")})
    st.download_button("Download hypotheses (JSON)", json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False),
                       file_name="grounded_hypotheses.json", mime="application/json")
