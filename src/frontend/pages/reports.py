import json

import streamlit as st

from src.frontend import components as ui
from src.frontend.utils import state
from src.frontend.utils.files import make_zip, read_if_exists

state.init_state()
ui.page_header("Results and Reports", "Everything generated in this session, with downloads and the agent run trace.")
s = st.session_state
files = {}
if s["hypothesis_report"] is not None:
    files["hypotheses/grounded_hypotheses.json"] = json.dumps(s["hypothesis_report"].model_dump(mode="json"), indent=2, ensure_ascii=False).encode()
for c in s["chart_results"]:
    if c["ok"]:
        files[f"charts/{c['name']}.extraction.json"] = json.dumps(c["data"], indent=2).encode()
build = s["paper_build"]
if build:
    synthesis, comp = build["synthesis"], build["compile"]
    for label, path in (("generated_research_paper.tex", synthesis.tex_path), ("references.bib", synthesis.bib_path),
                        ("generated_research_paper.pdf", comp.pdf_path if comp and comp.pdf_ok else None)):
        content = read_if_exists(path)
        if content:
            files[f"paper/{label}"] = content
    for path in (comp.fallback_files if comp else []):
        content = read_if_exists(path)
        if content:
            files["paper/" + path.replace("\\", "/").split("/")[-1]] = content
if s["trace"]:
    files["run_trace.json"] = json.dumps(s["trace"], indent=2).encode()

tab_dl, tab_trace, tab_cite = st.tabs(["Downloads", "Run trace", "Citations"])
with tab_dl:
    if not files:
        st.info("Nothing generated yet. Run a step on the other pages first.")
    else:
        for name, content in files.items():
            st.download_button(f"Download {name}", content, file_name=name.split("/")[-1], key=f"dl_{name}")
        st.download_button("Download everything (ZIP)", make_zip(files), file_name="discovery_agent_results.zip",
                           mime="application/zip", type="primary")
with tab_trace:
    st.markdown("**Workflow (colour = real status)**")
    st.graphviz_chart(ui.logic_tree_dot())
    ui.workflow_steps()
    st.markdown("**Agent run trace** (model, wall-clock time, outcome)")
    ui.trace_table()
    st.caption("Token usage and monetary cost are not available: the backend LLM client does not return usage data.")
with tab_cite:
    report = s["hypothesis_report"]
    titles = {c.get("paper_id") or c.get("arxiv_id") or c.get("pmid"): c.get("title", "") for c in s["chunks"]}
    if report is None or not report.hypotheses:
        st.info("Citations appear after hypotheses are generated.")
    else:
        rows = [{"hypothesis": h.title, "paper_id": p, "paper_title": titles.get(p, "")}
                for h in report.hypotheses for p in h.cited_paper_ids]
        st.dataframe(rows, width="stretch", hide_index=True)
