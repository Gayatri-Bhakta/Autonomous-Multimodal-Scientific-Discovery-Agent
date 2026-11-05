import html

import streamlit as st


AGENTS = [
    "Literature Reviewer",
    "Hypothesis Generator",
    "Code Executor",
    "Debugger Node",
    "Critic Node",
    "LaTeX Synthesizer",
]


def _canonical_agent(name: str | None) -> str | None:
    if not name:
        return None
    normalized = " ".join(name.replace("_", " ").split()).casefold()
    aliases = {
        "literature reviewer": "Literature Reviewer",
        "hypothesis generator": "Hypothesis Generator",
        "code executor": "Code Executor",
        "debugger": "Debugger Node",
        "debugger node": "Debugger Node",
        "critic": "Critic Node",
        "critic node": "Critic Node",
        "latex synthesizer": "LaTeX Synthesizer",
    }
    return aliases.get(normalized, name)


def render_agent_trace(
    active_agent: str | None = None,
    completed_agents: set[str] | list[str] | None = None,
    failed: bool = False,
) -> None:
    """Render the workflow as a styled, accessible sequence of agent cards."""
    active = _canonical_agent(active_agent)
    completed = {_canonical_agent(agent) for agent in (completed_agents or [])}

    st.markdown(
        """
        <style>
        .agent-flow { max-width: 880px; margin: .5rem auto 1rem; }
        .agent-card { display:flex; align-items:center; gap:14px; padding:15px 18px;
          margin:0; border:1px solid #334155; border-radius:14px;
          background:linear-gradient(110deg,#151c27,#111720); color:#e7edf5; }
        .agent-card.complete { border-color:#20734f; background:linear-gradient(110deg,#123526,#14251f); }
        .agent-card.active { border-color:#3389ff; background:linear-gradient(110deg,#102e50,#142337);
          box-shadow:0 0 22px rgba(51,137,255,.18); }
        .agent-card.error { border-color:#a83845; background:linear-gradient(110deg,#421c25,#27191e); }
        .agent-icon { display:grid; place-items:center; width:36px; height:36px;
          border-radius:50%; background:#293344; font-size:17px; flex:none; }
        .complete .agent-icon { background:#1e704b; }
        .active .agent-icon { background:#1766ba; }
        @keyframes activePulse { 0%,100% { box-shadow:0 0 0 0 rgba(80,164,255,.35); }
          50% { box-shadow:0 0 0 7px rgba(80,164,255,0); } }
        .active .agent-icon { animation:activePulse 1.7s ease-in-out infinite; }
        @media (prefers-reduced-motion: reduce) { .active .agent-icon { animation:none; } }
        .error .agent-icon { background:#a83243; }
        .agent-title { font-weight:650; font-size:1.02rem; }
        .agent-state { margin-left:auto; color:#a8b4c5; font-size:.82rem; }
        .complete .agent-state { color:#74e0a8; }
        .active .agent-state { color:#80bcff; }
        .error .agent-state { color:#ff9ba5; }
        .agent-connector { color:#718096; text-align:center; height:28px; line-height:28px; font-size:18px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    cards = []
    for index, agent in enumerate(AGENTS):
        if failed and agent == active:
            state, icon, label = "error", "!", "Needs attention"
        elif agent == active:
            state, icon, label = "active", "➤", "Latest update"
        elif agent in completed:
            state, icon, label = "complete", "✓", "Complete"
        else:
            state, icon, label = "", str(index + 1), "Waiting"
        cards.append(
            f'<div class="agent-card {state}">'
            f'<span class="agent-icon">{icon}</span>'
            f'<span class="agent-title">{html.escape(agent)}</span>'
            f'<span class="agent-state">{label}</span></div>'
        )
        if index < len(AGENTS) - 1:
            cards.append('<div class="agent-connector" aria-hidden="true">↓</div>')

    st.markdown(
        '<div class="agent-flow" role="list" aria-label="Research agent workflow">'
        + "".join(cards)
        + "</div>",
        unsafe_allow_html=True,
    )
