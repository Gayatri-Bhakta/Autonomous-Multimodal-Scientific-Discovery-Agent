# Cost and Latency Tracking

Prepared by: Sachin R Nair (Member 5)
Code: `src/utils/cost_tracker.py`, `dashboard/components/cost_analytics.py`
Tests: `tests/test_cost_tracker.py`, `tests/test_cost_analytics.py`, `tests/test_end_to_end.py`

## What it does

- Logs prompt tokens, completion tokens, dollar cost and latency for each agent, and totals them per discovery run.
- Times every node of the LangGraph pipeline, and each experiment, even when no LLM is called.
- Saves runs to a JSON log that the Streamlit widget reads.

## Hook it into the pipeline (no agent is edited)

```python
from src.orchestrator import build_orchestrator
from src.utils.cost_tracker import CostTracker, append_run, track_pipeline

tracker = CostTracker(label=topic)
with track_pipeline(tracker):                       # build AND run the graph inside this block
    app = build_orchestrator(enable_critic=True)
    result = app.invoke({"research_topic": topic, "enable_critic": True})
append_run(tracker)                                  # adds the run to output/cost_log.json
```

To record real LLM usage, wrap an LLM client (any object with `complete(prompt) -> str`):

```python
llm = tracker.wrap_llm(llm_client_from_env(), agent="hypothesis_generator", model="gpt-4o")
```

If the client sets `last_usage = {"prompt_tokens": ..., "completion_tokens": ...}` after each call, those
exact numbers are used. Otherwise the counts are estimated.

## Show it in the dashboard

```python
from dashboard.components.cost_analytics import render_cost_analytics
render_cost_analytics()          # reads output/cost_log.json, or render_cost_analytics(tracker=tracker)
```

The widget shows total cost, tokens, LLM calls and LLM time, plus three charts: cumulative cost per run, token
distribution by agent, and time per agent node. To preview it with demo data:
`streamlit run dashboard/components/cost_analytics.py`. It needs `plotly` and `streamlit`.

## How to read the numbers

- **Estimated tokens.** When a provider reports no token counts, they are estimated at about 4 characters per token.
  Every record is marked as estimated, and the dashboard says so.
- **Prices are placeholders.** The default price table is editable and is not an official price list. Check the
  provider's pricing page, and pass your own table: `CostTracker(pricing={"my-model": (input, output)})`
  (USD per 1,000,000 tokens).
- **Unknown prices are not free.** A model with no known price has cost "unknown", is counted separately, and the
  dashboard warns about it. Local models (Ollama, llama, and similar) cost 0.
- **Offline agents cost nothing.** The rule-based agents make no LLM calls, so tokens and cost are 0 and the widget
  shows node timings instead.

## Tests

```bash
python -m pytest tests/test_cost_tracker.py tests/test_cost_analytics.py tests/test_end_to_end.py -q
```

`tests/test_end_to_end.py` runs the whole pipeline offline (query, ingestion, vector DB, retrieval, hypothesis,
execution, self-debugging, critic, cost tracking) without network, API keys or Docker, and writes nothing into the
repository. Tests for `main.py` and the paper stage skip until those files exist in the branch. Four tests record
known problems in the paper stage as expected failures; they turn into passes once those problems are fixed.
