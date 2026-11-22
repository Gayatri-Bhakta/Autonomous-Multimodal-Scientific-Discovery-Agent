import streamlit as st

from src.frontend import components as ui
from src.frontend.services.status import environment_status, module_status
from src.frontend.utils import state

state.init_state()
ui.page_header("Autonomous Multimodal Scientific Discovery Agent",
               "Collect literature, ground hypotheses in evidence, read charts with a vision model, "
               "and draft a LaTeX research paper.")
modules, env = module_status(), environment_status()
ready = sum(m["state"] == "ready" for m in modules)

cols = st.columns(4)
with cols[0]:
    ui.card("Modules ready", f"{ready} / {len(modules)}", "connected and configured")
with cols[1]:
    ui.card("LLM", "Configured" if env["llm"]["configured"] else "Not configured", env["llm"]["model"] or "set LLM_* variables")
with cols[2]:
    ui.card("Vision model", "Configured" if env["vision"]["configured"] else "Not configured", env["vision"]["model"] or "needed for charts")
with cols[3]:
    ui.card("LaTeX (pdflatex)", "Available" if env["latex"]["available"] else "Not found", "PDF output" if env["latex"]["available"] else "HTML/Markdown fallback")

st.subheader("Agents and module status")
for m in modules:
    c1, c2, c3 = st.columns([2, 2, 5])
    c1.markdown(f"**{m['week']}**  \n{m['name']}")
    c2.markdown(ui.badge(m["state"]), unsafe_allow_html=True)
    c3.caption(f"`{m['module']}` - {m['detail']}")

st.subheader("Research workflow")
ui.workflow_steps()

left, right = st.columns(2)
with left:
    st.subheader("Uploaded documents")
    if st.session_state["uploads"]:
        st.dataframe(st.session_state["uploads"], width="stretch", hide_index=True)
    else:
        st.info("Nothing uploaded in this session yet.")
with right:
    st.subheader("Generated results")
    report, build, charts = st.session_state["hypothesis_report"], st.session_state["paper_build"], st.session_state["chart_results"]
    rows = [("Hypotheses validated", len(report.hypotheses) if report else 0),
            ("Charts read", sum(c["ok"] for c in charts)),
            ("Paper draft", build["synthesis"].status if build else "not generated")]
    st.table({"Result": [r[0] for r in rows], "Value": [str(r[1]) for r in rows]})

st.subheader("Application status")
if not env["llm"]["configured"]:
    st.warning("No LLM configured: hypothesis generation and LLM-written paper sections are disabled. See the README.")
else:
    st.success("LLM configured.")
if env["code_execution_enabled"]:
    st.info("Code execution switch is ON (local use only).")
