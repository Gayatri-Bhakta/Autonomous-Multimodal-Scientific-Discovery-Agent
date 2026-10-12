# Agent Role Specifications & State Flow

## 1. System Overview
The ScientiaAgent system orchestrates three specialized autonomous agents via LangGraph:
1. **Literature Reviewer** (Member 2)
2. **Hypothesis Generator** (Member 2)
3. **Code Executor** (Member 5)

---

## 2. Agent Contracts & State Schema

### State Object (`AgentGraphState`)
* `research_topic` (str): Domain query (e.g., "Transformer Memory Optimization").
* `literature_summary` (str): Output from Literature Reviewer summarizing papers and identifying research gaps.
* `generated_hypotheses` (List[str]): Candidate hypotheses proposed by Hypothesis Generator.
* `selected_hypothesis` (str): Best candidate selected for experimental validation.
* `generated_code` (str): Standalone Python script created by Code Executor.
* `execution_result` (str): Raw output and metric deltas from sandbox execution.
* `logs` (List[str]): Chronological audit trail using `operator.add`.

---

## 3. Node Specifications

### Node 1: `literature_reviewer`
* **Input:** `research_topic`, retrieved papers from Vector DB.
* **Processing:** Synthesize state-of-the-art literature and pinpoint unsolved bottlenecks.
* **Output:** `literature_summary`, `logs`.

### Node 2: `hypothesis_generator`
* **Input:** `literature_summary`.
* **Processing:** Formulate falsifiable, novel scientific hypotheses grounded in literature.
* **Output:** `generated_hypotheses`, `selected_hypothesis`, `logs`.

### Node 3: `code_executor`
* **Input:** `selected_hypothesis`.
* **Processing:** Generate and execute self-contained Python experiments.
* **Output:** `generated_code`, `execution_result`, `logs`.