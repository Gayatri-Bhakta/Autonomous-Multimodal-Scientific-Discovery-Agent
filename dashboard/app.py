from components.agent_trace import AGENTS, render_agent_trace
from components.paper_viewer import render_paper_viewer

import streamlit as st


st.set_page_config(
    page_title="Scientific Discovery Dashboard",
    page_icon="🔬",
    layout="wide",
)

st.title("Autonomous Scientific Discovery Agent")
st.caption("Monitor research runs, agent progress, and generated papers.")

page = st.sidebar.radio(
    "Dashboard",
    [
        "Discovery Studio",
        "Agent Logic Tree",
        "Literature & Citations",
        "Paper Viewer",
    ],
)

if page == "Discovery Studio":
    st.header("Discovery Studio")
    topic = st.text_input("Research topic")
    sandbox = st.selectbox("Execution environment", ["Docker"])

    if "run_state" not in st.session_state:
        st.session_state["run_state"] = {}
        st.session_state["active_agent"] = "Waiting to start"

    if st.button("Start discovery"):
        if not topic.strip():
            st.warning("Enter a research topic first.")
        else:
            try:
                from src.orchestrator import build_orchestrator

                graph = build_orchestrator(enable_critic=True)
                run_state = {}

                with st.status("Discovery is running...", expanded=True) as status:
                    for event in graph.stream(
                        {
                            "research_topic": topic.strip(),
                            "enable_critic": True,
                        },
                        stream_mode="updates",
                    ):
                        for node_name, update in event.items():
                            run_state.update(update)
                            active_agent = node_name.replace("_", " ").title()
                            st.session_state["active_agent"] = active_agent

                            status.write(f"Running: {active_agent}")
                            for log in update.get("logs", []):
                                status.write(log)

                            st.session_state["run_state"] = run_state.copy()

                    status.update(
                        label="Discovery finished",
                        state="complete",
                    )

            except Exception as exc:
                st.error(f"Discovery failed: {exc}")

    run_state = st.session_state["run_state"]
    st.subheader("Run progress")
    st.write(f"Active agent: {st.session_state['active_agent']}")
    st.write(f"Sandbox result: {run_state.get('execution_status', 'Not started')}")
    st.write(f"Retries: {run_state.get('retry_count', 0)}")

    if run_state.get("execution_result"):
        with st.expander("Latest execution output"):
            st.code(run_state["execution_result"])


elif page == "Agent Logic Tree":
    st.header("Agent Logic Tree")

    active_agent = st.session_state.get("active_agent")
    if active_agent in AGENTS:
        st.caption(f"Latest agent update: {active_agent}")
    else:
        st.info("Start a discovery run to see its agent progress.")

    render_agent_trace(active_agent if active_agent in AGENTS else None)

elif page == "Literature & Citations":
    st.header("Literature & Citation Explorer")
    query = st.text_input("Search stored papers")
    top_k = st.slider("Number of results", min_value=1, max_value=10, value=5)
    min_score = st.slider(
    "Minimum similarity",
    min_value=0.0,
    max_value=0.5,
    value=0.0,
    step=0.05,
)

    if st.button("Search papers", disabled=not query.strip()):
        try:
            from src.rag.retriever import get_relevant_literature

            papers = get_relevant_literature(
    query,
    top_k=top_k,
    min_score=min_score,
)

            if not papers:
                st.info("No matching papers found.")
            else:
                for paper in papers:
                    with st.container(border=True):
                        st.subheader(
                            f"{paper.get('rank', '')}. "
                            f"{paper.get('title') or paper.get('paper_id', 'Untitled paper')}"
                        )
                        authors = ", ".join(paper.get("authors") or [])
                        st.caption(
                            f"{authors or 'Authors unavailable'} · "
                            f"{paper.get('year') or 'Year unknown'} · "
                            f"{paper.get('source', 'unknown')}"
                        )
                        st.write(paper.get("snippet") or "No text snippet available.")
                        st.write(
                            f"Paper ID: {paper.get('paper_id', 'unknown')} · "
                            f"Similarity: {paper.get('similarity', 'unknown')}"
                        )
                        if paper.get("url"):
                            st.link_button("Open paper", paper["url"])

        except Exception as exc:
            st.error(f"Paper search failed: {exc}")

elif page == "Paper Viewer":
    st.header("Generated Paper")
    render_paper_viewer()