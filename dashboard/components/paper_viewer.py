from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_PAPER = PROJECT_ROOT / "output" / "generated_research_paper.pdf"


def render_paper_viewer() -> None:
    """Preview and download the generated research paper."""
    pdf_bytes = None
    file_name = GENERATED_PAPER.name

    if GENERATED_PAPER.exists():
        pdf_bytes = GENERATED_PAPER.read_bytes()
        st.caption(f"Showing: {GENERATED_PAPER}")
    else:
        st.info("No generated paper found yet. Upload a PDF to preview it.")
        uploaded_file = st.file_uploader("Choose a PDF", type=["pdf"])

        if uploaded_file is not None:
            pdf_bytes = uploaded_file.getvalue()
            file_name = uploaded_file.name

    if pdf_bytes is None:
        return

    st.download_button(
        "Download PDF",
        data=pdf_bytes,
        file_name=file_name,
        mime="application/pdf",
    )

    st.pdf(pdf_bytes, height=700, alt=f"Preview of {file_name}")