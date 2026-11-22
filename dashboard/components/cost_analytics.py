"""
Cost analytics widget for the Streamlit dashboard
Member 5 Deliverable (Week 4)

Two Plotly charts built from the runs a CostTracker saved:
  1. Cumulative cost ($) per discovery run
  2. Token distribution by agent (prompt vs completion tokens)

Use it inside any dashboard page:

    from dashboard.components.cost_analytics import render_cost_analytics
    render_cost_analytics()                      # reads output/cost_log.json
    render_cost_analytics(tracker=my_tracker)    # or show a live run

The figure builders (cumulative_cost_figure, token_distribution_figure) are plain functions that
return Plotly figures, so they can be tested and reused without Streamlit.
To preview the widget on its own with DEMO data:
    streamlit run dashboard/components/cost_analytics.py
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from src.utils.cost_tracker import DEFAULT_LOG_PATH, CostTracker, format_cost, load_runs
except ImportError:  # started with `streamlit run dashboard/app.py`: the repo root is not on sys.path yet
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.utils.cost_tracker import DEFAULT_LOG_PATH, CostTracker, format_cost, load_runs


def _go():
    import plotly.graph_objects as go  # imported here so the project works without Plotly installed

    return go


def run_label(run: Dict[str, Any]) -> str:
    return run.get("label") or run.get("run_id") or "run"


# ---------------------------------------------------------------------------
# Chart 1: cumulative cost per run
# ---------------------------------------------------------------------------
def cumulative_cost_figure(runs: List[Dict[str, Any]]):
    """One line per run: the running total cost after each LLM call (call 0 = $0)."""
    go = _go()
    fig = go.Figure()
    for run in runs:
        records = run.get("records", [])
        running, xs, ys, notes = 0.0, [0], [0.0], ["start"]
        for number, rec in enumerate(records, start=1):
            cost = rec.get("cost_usd")
            running += cost or 0.0
            xs.append(number)
            ys.append(running)
            notes.append(f"{rec.get('agent', '?')} ({rec.get('model', '?')})" + ("" if cost is not None else ", price unknown"))
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines+markers", name=run_label(run), text=notes,
                                 hovertemplate="call %{x}: %{text}<br>cumulative $%{y:.4f}<extra></extra>"))
    fig.update_layout(title="Cumulative cost per discovery run", xaxis_title="LLM call number",
                      yaxis_title="Cumulative cost (USD)", yaxis_tickformat="$.4f", legend_title="Run")
    if not runs:
        fig.add_annotation(text="No runs recorded yet", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


# ---------------------------------------------------------------------------
# Chart 2: token distribution by agent
# ---------------------------------------------------------------------------
def token_distribution_figure(run: Optional[Dict[str, Any]]):
    """Stacked bars: prompt and completion tokens for each agent, largest first."""
    go = _go()
    agents = {name: a for name, a in (run or {}).get("by_agent", {}).items() if a.get("total_tokens", 0) > 0}
    names = sorted(agents, key=lambda n: agents[n]["total_tokens"], reverse=True)
    fig = go.Figure()
    fig.add_bar(name="Prompt tokens", x=names, y=[agents[n]["prompt_tokens"] for n in names])
    fig.add_bar(name="Completion tokens", x=names, y=[agents[n]["completion_tokens"] for n in names])
    title = "Token distribution by agent"
    if run and run.get("estimated_calls"):
        title += " (includes estimated counts)"
    fig.update_layout(barmode="stack", title=title, xaxis_title="Agent", yaxis_title="Tokens")
    if not names:
        fig.add_annotation(text="No token usage recorded", showarrow=False, xref="paper", yref="paper", x=0.5, y=0.5)
    return fig


# ---------------------------------------------------------------------------
# The Streamlit widget
# ---------------------------------------------------------------------------
def agent_table(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-agent rows for a table."""
    rows = []
    for name, a in sorted(run.get("by_agent", {}).items(), key=lambda item: item[1].get("total_tokens", 0), reverse=True):
        rows.append({
            "Agent": name,
            "Calls": a.get("calls", 0),
            "Prompt tokens": a.get("prompt_tokens", 0),
            "Completion tokens": a.get("completion_tokens", 0),
            "Cost": format_cost(a.get("cost_usd", 0.0)),
            "LLM time (s)": round(a.get("latency_s", 0.0), 2),
        })
    return rows


def render_cost_analytics(
    st: Any = None,
    runs: Optional[List[Dict[str, Any]]] = None,
    log_path: str = DEFAULT_LOG_PATH,
    tracker: Optional[CostTracker] = None,
    key_prefix: str = "cost",
) -> None:
    """Draw the cost widget. Data comes from `tracker` (live run), `runs`, or the log file, in that order."""
    if st is None:
        import streamlit as st  # noqa: F811

    if tracker is not None:
        runs = [tracker.to_dict()]
    elif runs is None:
        runs = load_runs(log_path)

    st.subheader("Execution cost analytics")
    if not runs:
        st.info("No cost data yet. Run a discovery with the cost tracker enabled; runs are saved to "
                f"`{log_path}`.")
        return

    labels = [run_label(r) for r in runs]
    chosen = st.selectbox("Discovery run", labels, index=len(labels) - 1, key=f"{key_prefix}_run")
    run = runs[labels.index(chosen)]

    columns = st.columns(4)
    columns[0].metric("Total cost", format_cost(run.get("total_cost_usd", 0.0)))
    columns[1].metric("Total tokens", f"{run.get('total_tokens', 0):,}")
    columns[2].metric("LLM calls", run.get("calls", 0))
    columns[3].metric("LLM time", f"{run.get('llm_latency_s', 0.0):.1f} s")

    if run.get("estimated_calls"):
        st.caption(f"{run['estimated_calls']} of {run.get('calls', 0)} calls use estimated token counts "
                   "(about 4 characters per token), not provider-reported numbers.")
    if run.get("unpriced_calls"):
        st.warning(f"{run['unpriced_calls']} call(s) used a model with no known price. Their cost is NOT included in the total.")
    for exp in run.get("experiments", []):
        st.caption(f"Experiment `{exp.get('name')}`: {exp.get('latency_s', 0.0):.2f} s")

    st.plotly_chart(cumulative_cost_figure(runs), key=f"{key_prefix}_cumulative")
    st.plotly_chart(token_distribution_figure(run), key=f"{key_prefix}_tokens")
    rows = agent_table(run)
    if rows:
        st.dataframe(rows)


def demo_runs() -> List[Dict[str, Any]]:
    """Two small made-up runs, ONLY for previewing the widget (always labelled as demo data)."""
    runs = []
    for number, scale in ((1, 1), (2, 2)):
        tracker = CostTracker(run_id=f"demo-{number}", label=f"DEMO run {number}")
        tracker.record("hypothesis_generator", "gpt-4o", 1800 * scale, 400 * scale, latency_s=2.1)
        tracker.record("code_executor", "gpt-4o", 2500 * scale, 900 * scale, latency_s=3.4)
        tracker.record("debugger", "gpt-4o", 1200 * scale, 300 * scale, latency_s=1.8, estimated=True)
        tracker.record("critic", "gpt-4o", 900 * scale, 350 * scale, latency_s=1.2)
        runs.append(tracker.to_dict())
    return runs


if __name__ == "__main__":  # streamlit run dashboard/components/cost_analytics.py
    import streamlit as _st

    _st.caption("Preview with DEMO data (not a real run).")
    render_cost_analytics(_st, runs=demo_runs())
