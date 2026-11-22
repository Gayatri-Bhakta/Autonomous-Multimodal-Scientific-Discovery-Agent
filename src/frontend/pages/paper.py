import pandas as pd
import streamlit as st

from src.frontend import components as ui
from src.frontend.services import hypothesis as hyp_service
from src.frontend.services import paper as paper_service
from src.frontend.services.status import latex_status
from src.frontend.utils import state
from src.frontend.utils.env import llm_status
from src.frontend.utils.files import read_if_exists, save_upload, validate_upload

state.init_state()
ui.page_header("Research Paper Generation", "Week 4: LaTeX draft, references.bib and PDF from your verified results.")
llm, latex = llm_status(), latex_status()
selected = st.session_state["selected_hypothesis"]
chunks = st.session_state["chunks"]

st.info("The LLM only writes prose. Numbers, p-values, the results table, figures and references come from the data you "
        "enter below. Enter only results that were really measured (or tick 'simulated').")

st.subheader("1. Paper details")
title = st.text_input("Title")
authors_text = st.text_area("Authors (one per line: Name | Affiliation)", height=80)
hyp_default = hyp_service.hypothesis_to_paper_text(selected) if selected else ""
if selected:
    st.caption("Hypothesis pre-filled from the Hypothesis page; edit freely.")
hypothesis = st.text_area("Hypothesis / research objective", value=hyp_default, height=110)
setup = st.text_area("Experimental setup (facts only: data, models, seeds, hardware)", height=110)
limitations = st.text_area("Limitations (one per line)", height=70)

st.subheader("2. Verified results")
seed = st.session_state["paper_results_seed"]
if seed is None:
    seed = pd.DataFrame({"method": pd.Series(dtype="object"), "metric": pd.Series(dtype="object"),
                         "value": pd.Series(dtype="float"), "std": pd.Series(dtype="float"),
                         "n": pd.Series(dtype="Int64"), "p_value": pd.Series(dtype="float"),
                         "comparison": pd.Series(dtype="object")})
edited = st.data_editor(seed, num_rows="dynamic", width="stretch", key="results_editor")

st.subheader("3. Figures and references")
figure_specs = []
for img in st.session_state["chart_images"]:
    if st.checkbox(f"Include chart image: {img['name']}", key=f"fig_{img['name']}"):
        caption = st.text_input("Caption", key=f"cap_{img['name']}")
        figure_specs.append({"path": img["path"], "caption": caption or None})
extra = st.file_uploader("Add figure files (PNG, JPG, PDF)", type=["png", "jpg", "jpeg", "pdf"], accept_multiple_files=True)
for f in extra or []:
    error = validate_upload(f.name, f.getvalue(), (".png", ".jpg", ".jpeg", ".pdf"), 10)
    if error:
        st.error(error)
    else:
        path = save_upload(f.getvalue(), f.name, state.OUTPUT_DIR / "figures")
        figure_specs.append({"path": str(path), "caption": None})
ref_options = [m["paper_id"] for m in paper_service.metas_from_chunks(chunks)]
default_refs = (selected or {}).get("cited_paper_ids", []) if selected else []
cited = st.multiselect("References to include (from the loaded evidence)", ref_options,
                       default=[r for r in default_refs if r in ref_options])

st.subheader("4. Generate")
o1, o2, o3 = st.columns(3)
simulated = o1.checkbox("Results are simulated / illustrative")
use_llm = o2.checkbox("Write sections with the LLM", value=bool(llm["configured"]), disabled=not llm["configured"])
want_pdf = o3.checkbox("Compile to PDF", value=True)
if not latex["available"]:
    st.warning("pdflatex was not found. A PDF cannot be built; an HTML/Markdown fallback will be produced instead.")
if not llm["configured"]:
    st.caption("No LLM configured: prose sections will be clearly marked placeholders.")
confirmed = st.checkbox("I confirm the results above are verified (or marked simulated) and not invented")

rows = []
for rec in edited.to_dict("records"):
    clean = {k: (None if pd.isna(v) else v) for k, v in rec.items()}
    if clean.get("method") or clean.get("metric") or clean.get("value") is not None:
        if clean.get("n") is not None:
            clean["n"] = int(clean["n"])
        rows.append(clean)

if st.button("Generate paper", type="primary", disabled=not (title.strip() and rows and confirmed)):
    data = {"title": title.strip(), "authors": paper_service.parse_authors(authors_text),
            "hypothesis": hypothesis.strip() or None, "experimental_setup": setup.strip() or None, "results": rows,
            "figures": figure_specs, "papers": paper_service.metas_from_chunks(chunks, cited),
            "limitations": paper_service.parse_lines(limitations), "is_simulated": simulated}
    with st.spinner("Writing sections, building references and compiling..."):
        res = paper_service.build_paper(data, state.OUTPUT_DIR / "paper", use_llm=use_llm and bool(llm["configured"]),
                                        compile_pdf=want_pdf)
    state.add_trace("Paper generation", "ok" if res.ok else "error", res.seconds, res.message,
                    (llm["model"] or "") if use_llm else "no LLM")
    ui.show_result(res)
    if res.data:
        st.session_state["paper_build"] = res.data

build = st.session_state["paper_build"]
if build:
    synthesis, comp = build["synthesis"], build["compile"]
    st.subheader("5. Output")
    st.markdown(f"**Status:** `{synthesis.status}`" + (" - SIMULATED DATA" if synthesis.is_simulated else ""))
    st.table({"Section": list(synthesis.sections), "Source": [v if len(v) < 90 else v[:87] + "..." for v in synthesis.sections.values()]})
    for w in synthesis.warnings:
        st.warning(w)
    if comp is None:
        st.info("Compilation was skipped.")
    elif comp.pdf_ok:
        st.success(f"PDF generated with {comp.engine}.")
    else:
        st.error(f"No PDF was generated: {comp.message}")
        for e in comp.errors[:5]:
            st.code(e)
        if comp.fallback_files:
            st.info("HTML / Markdown fallback files were written instead.")
    tex_bytes, bib_bytes = read_if_exists(synthesis.tex_path), read_if_exists(synthesis.bib_path)
    d = st.columns(5)
    if tex_bytes:
        d[0].download_button("LaTeX (.tex)", tex_bytes, file_name="generated_research_paper.tex", mime="application/x-tex")
    if bib_bytes:
        d[1].download_button("References (.bib)", bib_bytes, file_name="references.bib", mime="text/plain")
    if comp and comp.pdf_ok:
        d[2].download_button("PDF", read_if_exists(comp.pdf_path) or b"", file_name="generated_research_paper.pdf", mime="application/pdf")
    for path in (comp.fallback_files if comp else []):
        data_b = read_if_exists(path)
        if data_b:
            slot = d[3] if path.endswith(".html") else d[4]
            slot.download_button("HTML" if path.endswith(".html") else "Markdown", data_b, file_name=path.replace("\\", "/").split("/")[-1])
    with st.expander("LaTeX source"):
        st.code((tex_bytes or b"").decode("utf-8", "replace"), language="latex")
