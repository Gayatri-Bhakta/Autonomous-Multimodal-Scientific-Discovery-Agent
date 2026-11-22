import streamlit as st

from src.frontend import components as ui
from src.frontend.services import literature as literature_service
from src.frontend.utils import state


state.init_state()

ui.page_header(
    "Literature Review",
    "Week 1: Search research papers, analyze themes, limitations and research gaps."
)

with st.form("literature_review_form"):
    topic = st.text_input(
        "Research topic",
        placeholder="Example: AI safety and deception detection in LLM agents"
    )
    max_papers = st.number_input(
        "Maximum papers",
        min_value=1,
        max_value=50,
        value=5,
        step=1
    )
    save_review = st.checkbox("Save review as JSON", value=True)
    submitted = st.form_submit_button("Run Literature Review")

if submitted:
    with st.spinner("Searching and analyzing research papers..."):
        response = literature_service.review(
            topic=topic,
            max_papers=int(max_papers),
            save=save_review
        )

    if response.ok:
        st.session_state["literature_review_result"] = response.data
        st.success(response.message)
        st.caption(f"Completed in {response.seconds:.2f} seconds.")
    else:
        st.error(response.message)

result = st.session_state.get("literature_review_result")

if result:
    st.divider()
    st.subheader(f"Research Papers: {result.topic}")

    if result.papers:
        rows = []
        for paper in result.papers:
            rows.append({
                "Title": paper.title,
                "arXiv ID": paper.arxiv_id,
                "Authors": ", ".join(paper.authors),
                "Published": paper.published,
                "URL": paper.url,
            })

        st.dataframe(rows, width="stretch", hide_index=True)

        st.subheader("Paper Details")
        for paper in result.papers:
            with st.expander(paper.title):
                st.write("**Authors:**", ", ".join(paper.authors))
                st.write("**Published:**", paper.published)
                st.write("**arXiv ID:**", paper.arxiv_id)
                st.write(paper.abstract)
                st.markdown(f"[Open Research Paper]({paper.url})")

    if result.analysis:
        analysis = result.analysis

        st.divider()
        st.subheader("Literature Analysis")

        for heading, findings in [
            ("Research Themes", analysis.themes),
            ("Limitations", analysis.limitations),
            ("Research Gaps", analysis.research_gaps),
        ]:
            st.markdown(f"**{heading}**")
            if findings:
                for finding in findings:
                    st.markdown(f"- {finding.text}")
                    if finding.source_ids:
                        st.caption("Sources: " + ", ".join(finding.source_ids))
            else:
                st.info(f"No {heading.lower()} identified.")

        if analysis.caveats:
            st.warning(analysis.caveats)

    if result.saved_path:
        st.caption(f"Saved review: {result.saved_path}")

else:
    st.info("Enter a research topic above to start a literature review.")
