# Mid-Project Review & Integration Report (Week 1 + Week 2)

**Project:** Autonomous Multimodal Scientific Discovery Agent (AutoScientist AI)  
**Organization:** Zaalima Development Pvt. Ltd. (DSML Enterprise Track)  
**Prepared by:** Team Lead (Member 1 - Gayatri Bhakta)  
**Milestone Window:** Mid-Review Milestone (16th – 22nd October 2026)  
**Branch:** `Gayatri-Bhakta` / `main`  

---

## 1. Executive Summary

In **Week 1**, the team established the baseline discovery pipeline: a 3-agent linear orchestration workflow (`Literature Reviewer` ➔ `Hypothesis Generator` ➔ `Code Executor`), data ingestion engines for arXiv and PubMed, ChromaDB vector storage, and an automated test suite passing with 100% test coverage across 72 unit tests.

In **Week 2 (Mid-Review Milestone)**, the system transitions from static mock placeholders to an **autonomous, self-healing scientific discovery engine**:
1. **Literature-Grounded RAG:** Grounding hypothesis formulation in peer-reviewed papers retrieved via cosine similarity.
2. **Containerized Docker Sandbox:** Isolating generated Python experiment execution inside locked containers with strict memory, CPU, and zero-network security constraints.
3. **Reflexion Self-Debugging Loop:** Replacing the linear workflow with a cyclic LangGraph state machine that intercepts execution errors and prompts an autonomous debugging agent to patch code iteratively (up to 3 retries).

---

## 2. Team Architecture & Responsibilities

| Role | Member | Primary Focus | Key Deliverables |
| :--- | :--- | :--- | :--- |
| **Member 1 (Lead)** | Gayatri Bhakta | Cyclic Orchestrator & StateGraph Integration | `src/orchestrator.py`<br>`docs/mid_review_report.md` |
| **Member 2** | Kabil | Hypothesis RAG Grounding & Pydantic Validation | `src/agents/hypothesis_agent.py`<br>`data/sample_grounded_hypotheses.json` |
| **Member 3** | Afrah | Vector Retrieval Engine & Context Formatting | `src/rag/retriever.py`<br>`tests/test_retriever.py` |
| **Member 4** | Abhishek | Containerized Docker Execution Sandbox | `sandbox/Dockerfile`<br>`src/sandbox/docker_runner.py`<br>`tests/test_sandbox_security.py` |
| **Member 5** | Sachin | Self-Debugging Reflexion Agent & Test Suite | `src/agents/debugger_agent.py`<br>`tests/test_debugging_loop.py`<br>`docs/debugging_traces.md` |

---

## 3. Cyclic StateGraph Architecture (Week 2 Upgrade)

```mermaid
flowchart TD
    START([START]) --> LitRev["Node 1: Literature Reviewer Agent\n(RAG Context via ChromaDB)"]
    LitRev --> HypGen["Node 2: Hypothesis Generator Agent\n(Grounded Hypotheses & Citations)"]
    HypGen --> CodeExec["Node 3: Code Executor Agent\n(Docker Sandbox / Subprocess)"]
    
    CodeExec --> Decision{"Router: execution_status"}
    Decision -->|"SUCCESS"| ENDNode([END: Discoveries Logged])
    Decision -->|"ERROR and retry_count < 3"| Debugger["Node 4: Debugger Agent\n(Reflexion Patch on Traceback)"]
    Debugger -->|"Repaired Code (retry_count++)"| CodeExec
    Decision -->|"retry_count >= 3"| AbortNode([END: Terminated / Max Retries])
```

### Shared State Schema (`AgentGraphState`)
* `research_topic` (`str`): Target scientific domain.
* `literature_summary` (`str`): Synthesized literature abstract analysis.
* `retrieved_papers` (`List[Dict]`): Context chunks retrieved from ChromaDB via cosine similarity thresholding.
* `generated_hypotheses` (`List[str]`): Candidate hypotheses adhering to `GroundedHypothesis` schema.
* `selected_hypothesis` (`str`): Top falsifiable hypothesis selected for empirical testing.
* `generated_code` (`str`): Experiment script executed in sandbox.
* `execution_result` (`str`): Terminal output, metric deltas, or stack trace.
* `execution_status` (`str`): Run outcome flag (`"SUCCESS"` or `"ERROR"`).
* `error_traceback` (`str`): Traceback consumed by the Debugger Agent during Reflexion cycles.
* `retry_count` (`int`): Iteration counter for self-healing loops (capped at 3).
* `logs` (`Annotated[List[str], operator.add]`): Immutable chronological audit log.

---

## 4. Implementation Calendar (Oct 16 – Oct 22)

* **Day 1 (Oct 16) - Interfaces & Setup:** StateGraph schema upgraded; `sandbox/` and `src/sandbox/` initialized; dependencies consolidated.
* **Day 2 (Oct 17) - Core Logic 1:** Docker runner implemented; ChromaDB connected to retrieval queries; Pydantic grounded models integrated.
* **Day 3 (Oct 18) - Core Logic 2:** Reflexion debugger implemented; Docker resource caps enforced (`network_mode="none"`, `mem_limit="1g"`).
* **Day 4 (Oct 19) - Integration:** Retriever connected to Hypothesis Generator; Docker code execution verified.
* **Day 5 (Oct 20) - Feedback Loop:** Sandbox failure connected to Debugger Agent for autonomous self-healing.
* **Day 6 (Oct 21) - Testing & Hardening:** Breakout prevention proved; full automated test suite verified.
* **Day 7 (Oct 22) - PR Reviews & Freeze:** Final integration of all member branches into `main` before the Mid-Review window opens.

---

## 5. Audit of Current Status (Day 1)

* **Test Suite Status:** 74/74 unit tests passing (100% green).
* **StateGraph Orchestrator:** Cyclic conditional loop operational with unit tests for `execution_router` and `debugger_node`.
* **Repository Health:** Clean directory structure with zero merge conflicts on `main`.
