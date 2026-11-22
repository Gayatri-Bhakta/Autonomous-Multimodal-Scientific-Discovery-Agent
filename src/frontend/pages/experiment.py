import streamlit as st

from src.frontend import components as ui
from src.frontend.services import executor as executor_service
from src.frontend.utils import state
from src.frontend.utils.env import code_execution_enabled

state.init_state()

ui.page_header(
    "Experiment / Code Execution",
    "Generate and preview experiment code safely. Execution is disabled."
)

st.info(
    "Code Preview only: generated Python code is displayed but never executed."
)

with st.form("experiment_preview_form"):
    hypothesis = st.text_area(
        "Research Hypothesis",
        placeholder="Example: Dynamic token pruning reduces inference memory by 30 percent."
    )
    submitted = st.form_submit_button("Generate Code Preview")

if submitted:
    response = executor_service.generate_preview(hypothesis)

    if response.ok:
        st.session_state["experiment_code_preview"] = response.data["code"]
        st.success(response.message)
    else:
        st.error(response.message)

code = st.session_state.get("experiment_code_preview")

if code:
    st.subheader("Generated Python Code")
    st.code(code, language="python")
    st.download_button(
        "Download Python Script",
        data=code,
        file_name="experiment_preview.py",
        mime="text/x-python"
    )
    st.warning("Not Executed — this is a code preview only.")

st.caption(
    f"ENABLE_CODE_EXECUTION switch: "
    f"{'ON' if code_execution_enabled() else 'OFF'}"
)
