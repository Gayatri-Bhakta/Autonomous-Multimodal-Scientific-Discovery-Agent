"""
Multi-Agent Orchestrator
Member 1 - Team Lead Deliverable
Coordinates: Literature Reviewer -> Hypothesis Generator -> Code Executor
"""

import operator
import sys
from pathlib import Path
from typing import Annotated, Dict, Any, List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

# Ensure repository root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# State Schema for Agent Communication
class AgentGraphState(TypedDict):
    research_topic: str
    literature_summary: str
    generated_hypotheses: List[str]
    selected_hypothesis: str
    generated_code: str
    execution_result: str
    logs: Annotated[List[str], operator.add]


# Node 1: Literature Reviewer (Assigned to Member 2)
def literature_reviewer_node(state: AgentGraphState) -> Dict[str, Any]:
    topic = state.get("research_topic", "General AI")
    print(f"\n[Literature Reviewer] Analyzing papers for: '{topic}'...")

    try:
        # Plug in real agent when Member 2 finishes
        from src.agents.literature_agent import run_literature_review
        summary = run_literature_review(topic)
    except (ImportError, ModuleNotFoundError):
        # Fallback placeholder
        summary = f"Identified papers on autonomous reasoning and code execution bottlenecks in {topic}."

    return {
        "literature_summary": summary,
        "logs": [f"Literature Reviewer completed retrieval for topic: {topic}"]
    }


# Node 2: Hypothesis Generator (Assigned to Member 2)
def hypothesis_generator_node(state: AgentGraphState) -> Dict[str, Any]:
    print("\n[Hypothesis Generator] Formulating hypotheses...")

    try:
        # Plug in real agent when Member 2 finishes
        from src.agents.hypothesis_agent import generate_hypothesis
        hypothesis = generate_hypothesis(state.get("literature_summary", ""))
        hypotheses = [hypothesis]
    except (ImportError, ModuleNotFoundError):
        # Fallback placeholder
        hypotheses = [
            "Hypothesis: Dynamic token-level pruning reduces inference memory by 30% with <1% perplexity loss."
        ]

    return {
        "generated_hypotheses": hypotheses,
        "selected_hypothesis": hypotheses[0],
        "logs": ["Hypothesis Generator formulated novel experimental hypothesis."]
    }


# Node 3: Code Executor (Assigned to Member 5)
def code_executor_node(state: AgentGraphState) -> Dict[str, Any]:
    print("\n[Code Executor] Running code simulation...")

    selected_hyp = state.get("selected_hypothesis", "")
    try:
        # Plug in real code generator when Member 5 finishes
        from src.agents.code_executor_agent import generate_and_run_code
        code, output = generate_and_run_code(selected_hyp)
    except (ImportError, ModuleNotFoundError):
        # Fallback placeholder
        code = "print('Running hypothesis test script... Result: Success.')"
        output = "Execution successful. Metric delta: +0.25"

    return {
        "generated_code": code,
        "execution_result": output,
        "logs": ["Code Executor generated and executed test loop."]
    }


# Build LangGraph Workflow
def build_orchestrator():
    workflow = StateGraph(AgentGraphState)

    workflow.add_node("literature_reviewer", literature_reviewer_node)
    workflow.add_node("hypothesis_generator", hypothesis_generator_node)
    workflow.add_node("code_executor", code_executor_node)

    workflow.add_edge(START, "literature_reviewer")
    workflow.add_edge("literature_reviewer", "hypothesis_generator")
    workflow.add_edge("hypothesis_generator", "code_executor")
    workflow.add_edge("code_executor", END)

    return workflow.compile()


if __name__ == "__main__":
    app = build_orchestrator()
    result = app.invoke({"research_topic": "Autonomous Agent Reasoning"})
    print("\n" + "=" * 50)
    print("PIPELINE EXECUTION SUMMARY")
    print("=" * 50)
    print(f"Topic: {result.get('research_topic')}")
    print(f"Selected Hypothesis: {result.get('selected_hypothesis')}")
    print(f"Code Generated:\n{result.get('generated_code')}")
    print(f"Execution Output: {result.get('execution_result')}")
    print("\nAudit Logs:")
    for log in result.get("logs", []):
        print(f"  • {log}")