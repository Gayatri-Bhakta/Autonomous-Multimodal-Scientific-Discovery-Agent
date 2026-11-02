"""
End-to-end test of the whole pipeline (Member 5, Week 4).

    python -m pytest tests/test_end_to_end.py -v

One command checks that a research query travels through every stage without crashing:

    query -> ingestion -> vector DB -> retrieval -> hypothesis -> code execution
          -> self-debugging -> statistics -> critic -> cost tracking -> paper generation

The test is hermetic: no network, no API keys, no Docker, and it writes nothing into the
repository (the scrapers are stubbed with the sample papers, the vector store and the
episodic memory live in a temporary folder, live arXiv calls are blocked).

The paper-generation stage and the master entrypoint (main.py) belong to other members. Their
tests are skipped with a clear reason until those files exist in the branch.
"""
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("chromadb")

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PAPERS = ROOT / "data" / "sample_scraped_papers.json"
TOPIC = "AI agent time horizons"
VERDICTS = {"ACCEPTED", "REJECTED", "NEEDS_REPLICATION"}
TIMED_NODES = {"literature_reviewer", "hypothesis_generator", "code_executor", "critic"}


# ---------------------------------------------------------------------------
# Hermetic environment, built once for the whole file
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def offline():
    """Block the network so nothing live is called (the agents fall back to local data)."""
    mp = pytest.MonkeyPatch()

    def no_urlopen(*args, **kwargs):
        raise urllib.error.URLError("network disabled for the end-to-end test")

    def no_dns(*args, **kwargs):
        raise socket.gaierror("network disabled for the end-to-end test")

    mp.setattr(urllib.request, "urlopen", no_urlopen)
    mp.setattr(socket, "getaddrinfo", no_dns)
    yield
    mp.undo()


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    return tmp_path_factory.mktemp("e2e")


@pytest.fixture(scope="module")
def ingested(offline, workspace):
    """Stage 1: the real ingestion pipeline, with the two scrapers returning the sample papers."""
    from src.ingestion import pipeline
    from src.ingestion.schema import load_papers

    sample = load_papers(SAMPLE_PAPERS)
    mp = pytest.MonkeyPatch()
    mp.setattr(pipeline.ArxivScraper, "search", lambda self, *a, **k: [p for p in sample if p.source == "arxiv"])
    mp.setattr(pipeline.PubMedScraper, "search", lambda self, *a, **k: [p for p in sample if p.source == "pubmed"])
    try:
        return pipeline.run_ingestion(["cs.AI"], "machine learning", incremental=False,
                                      state_path=workspace / "ingestion_state.json")
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def vector_db(ingested, workspace):
    """Stage 2: index the ingested papers in a temporary vector store."""
    from src.ingestion.schema import save_papers
    from src.rag.vector_db import ScientificVectorDB

    papers_file = save_papers(ingested, workspace / "papers.json")
    db = ScientificVectorDB(persist_directory=workspace / "vector_store")
    db.load_from_json(str(papers_file))
    return db


@pytest.fixture(scope="module")
def retriever(vector_db):
    """Stage 3: the retriever the orchestrator's literature node uses, pointed at the temporary store."""
    from src.rag import retriever as retriever_module

    ret = retriever_module.LiteratureRetriever(db=vector_db)
    mp = pytest.MonkeyPatch()
    mp.setattr(retriever_module, "_default_retriever", ret)
    yield ret
    mp.undo()


@pytest.fixture(scope="module")
def tracker():
    from src.utils.cost_tracker import CostTracker

    return CostTracker(run_id="end-to-end")


@pytest.fixture(scope="module")
def graph(retriever, workspace, tracker, offline):
    """The real LangGraph pipeline, with every node timed by the cost tracker."""
    from src import orchestrator
    from src.memory import episodic_memory

    mp = pytest.MonkeyPatch()
    mp.setattr(episodic_memory, "DEFAULT_STORAGE_PATH", workspace / "episodes.json")  # keep the repo clean
    for node, agent in (("literature_reviewer_node", "literature_reviewer"),
                        ("hypothesis_generator_node", "hypothesis_generator"),
                        ("code_executor_node", "code_executor"),
                        ("debugger_node", "debugger"),
                        ("critic_node", "critic")):
        mp.setattr(orchestrator, node, tracker.wrap_node(agent, getattr(orchestrator, node)))
    yield orchestrator.build_orchestrator(enable_critic=True)
    mp.undo()


@pytest.fixture(scope="module")
def normal_run(graph, tracker):
    """A full discovery run: query -> ... -> critic verdict."""
    with tracker.experiment("normal run"):
        return graph.invoke({"research_topic": TOPIC, "enable_critic": True})


@pytest.fixture(scope="module")
def debug_run(graph, tracker):
    """A run whose first experiment crashes (divide by zero) and must be repaired by the debugger."""
    crashing = "values = [4, 8, 15]\ncount = len([])\nprint('Baseline mean: 1')\nprint(sum(values) / count)\n"
    with tracker.experiment("self-debugging run"):
        return graph.invoke({"research_topic": TOPIC, "generated_code": crashing, "enable_critic": False})


# ---------------------------------------------------------------------------
# Stage 1-3: query -> ingestion -> vector DB -> retrieval
# ---------------------------------------------------------------------------
def test_ingestion_returns_valid_papers_from_both_sources(ingested):
    assert len(ingested) == 10
    assert {p.source for p in ingested} == {"arxiv", "pubmed"}
    assert all(p.is_valid() for p in ingested)


def test_ingested_papers_are_indexed(vector_db):
    assert vector_db.count() > 0


def test_retrieval_returns_papers_for_the_query(retriever, ingested):
    results = retriever.retrieve(TOPIC, top_k=3)
    assert 1 <= len(results) <= 3
    known_ids = {p.paper_id for p in ingested}
    for result in results:
        assert result["paper_id"] in known_ids
        assert result["title"] and result["snippet"]


# ---------------------------------------------------------------------------
# Stage 4-8: hypothesis -> execution -> critic, through the real graph
# ---------------------------------------------------------------------------
def test_full_run_finishes_and_fills_every_stage(normal_run):
    assert normal_run["literature_summary"].strip()
    assert normal_run["selected_hypothesis"].strip()
    assert normal_run["generated_code"].strip()
    assert normal_run["execution_status"] == "SUCCESS"
    assert normal_run["execution_result"].strip()


def test_literature_stage_used_the_temporary_vector_store(normal_run, ingested):
    titles = {p.title for p in ingested}
    retrieved = normal_run["retrieved_papers"]
    assert retrieved and all(r["title"] in titles for r in retrieved)


def test_experiment_output_contains_the_measurements(normal_run):
    assert "Metric delta" in normal_run["execution_result"]


def test_critic_gives_a_valid_verdict_and_the_loop_is_bounded(normal_run):
    assert normal_run["critic_verdict"] in VERDICTS
    assert normal_run["critic_critique"].strip()
    assert 1 <= normal_run["experiment_iteration"] <= 2


def test_self_debugging_repairs_a_crashing_experiment(debug_run):
    assert debug_run["execution_status"] == "SUCCESS"
    assert debug_run["retry_count"] == 1
    assert "or 1" in debug_run["generated_code"]  # the divisor guard added by the debugger


def test_episodic_memory_went_to_the_temporary_folder(normal_run, workspace):
    assert (workspace / "episodes.json").exists()


# ---------------------------------------------------------------------------
# Cost tracking across the real pipeline
# ---------------------------------------------------------------------------
def test_every_agent_stage_was_timed(normal_run, debug_run, tracker):
    assert TIMED_NODES <= set(tracker.node_latency_s)
    assert "debugger" in tracker.node_latency_s
    assert all(seconds > 0 for seconds in tracker.node_latency_s.values())


def test_each_experiment_has_a_latency(normal_run, debug_run, tracker):
    assert {e["name"] for e in tracker.experiments} == {"normal run", "self-debugging run"}
    assert all(e["latency_s"] > 0 for e in tracker.experiments)


def test_cost_summary_can_be_saved_and_reloaded(normal_run, tracker, tmp_path):
    from src.utils.cost_tracker import append_run, load_runs

    run = load_runs(append_run(tracker, tmp_path / "cost_log.json"))[0]
    assert run["run_id"] == "end-to-end"
    assert TIMED_NODES <= set(run["by_agent"])


def test_dashboard_charts_can_be_built_from_a_tracked_run(normal_run):
    pytest.importorskip("plotly")
    from dashboard.components.cost_analytics import cumulative_cost_figure, token_distribution_figure
    from src.utils.cost_tracker import CostTracker

    # No LLM is configured in this test, so one call is recorded by hand to give the charts data.
    run_tracker = CostTracker(run_id="charts")
    run_tracker.record("hypothesis_generator", "gpt-4o", 1200, 300, latency_s=0.1)
    run = run_tracker.to_dict()
    assert len(cumulative_cost_figure([run]).data) == 1
    assert len(token_distribution_figure(run).data) == 2


# ---------------------------------------------------------------------------
# Stages owned by other members: skipped until their files exist in this branch
# ---------------------------------------------------------------------------
def test_paper_generation_stage():
    pytest.importorskip("src.agents.synthesizer_agent",
                        reason="Member 2's synthesizer_agent.py is not in this branch yet")
    pytest.skip("synthesizer_agent.py exists now: extend this test with its real functions "
                "(verified numbers + citations -> .tex -> PDF or HTML fallback)")


def test_master_entrypoint_shows_help():
    entrypoint = ROOT / "main.py"
    if not entrypoint.exists():
        pytest.skip("main.py (Team Lead) is not in this branch yet")
    result = subprocess.run([sys.executable, str(entrypoint), "--help"], capture_output=True, text=True,
                            timeout=120, cwd=ROOT)
    assert result.returncode == 0 and "--topic" in result.stdout
