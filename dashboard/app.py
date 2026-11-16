"""AutoScientist AI — Discovery Dashboard"""
from pathlib import Path
import streamlit as st
from components.agent_trace import AGENTS, render_agent_trace
from components.paper_viewer import render_paper_viewer

st.set_page_config(
    page_title="AutoScientist AI",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════════════════════════
# GLOBAL STYLES
# ════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&family=JetBrains+Mono:wght@400;500&display=swap');

/* ─── Reset ─────────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"], .main { font-family:'Inter',sans-serif; background:#060912; color:#cbd5e1; }
#MainMenu, footer, header { visibility:hidden; }
.block-container { padding:0 !important; max-width:100% !important; }
section[data-testid="stMain"] > div { padding:0; }

/* ─── Sidebar ────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background:#07091a;
    border-right:1px solid rgba(139,92,246,.12);
    width:72px !important;
    min-width:72px !important;
}
[data-testid="stSidebar"] > div:first-child { width:72px; padding:0; }
[data-testid="stSidebarContent"] { padding:0; }
.stRadio > div { flex-direction:column; gap:0; }
.stRadio label { display:none !important; }

/* ─── Scrollbar ─────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width:6px; height:6px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:rgba(139,92,246,.3); border-radius:3px; }

/* ─── Main layout ───────────────────────────────────────────────────────── */
.app-shell {
    display:flex;
    min-height:100vh;
    background:#060912;
}
.nav-rail {
    width:72px;
    flex-shrink:0;
    display:flex;
    flex-direction:column;
    align-items:center;
    padding:20px 0;
    gap:4px;
    background:#07091a;
    border-right:1px solid rgba(139,92,246,.12);
    position:fixed;
    top:0;bottom:0;left:0;
    z-index:100;
}
.nav-logo {
    width:40px;height:40px;
    border-radius:12px;
    background:linear-gradient(135deg,#7c3aed,#06b6d4);
    display:flex;align-items:center;justify-content:center;
    font-size:1.2rem;
    margin-bottom:16px;
    box-shadow:0 0 20px rgba(124,58,237,.4);
}
.nav-divider { width:36px;height:1px;background:rgba(139,92,246,.15);margin:8px 0; }
.nav-btn {
    width:48px;height:48px;
    border-radius:14px;
    display:flex;align-items:center;justify-content:center;
    font-size:1.25rem;
    cursor:pointer;
    transition:all .2s cubic-bezier(.4,0,.2,1);
    color:#475569;
    position:relative;
}
.nav-btn:hover { background:rgba(139,92,246,.12); color:#a78bfa; }
.nav-btn.active {
    background:linear-gradient(135deg,rgba(124,58,237,.25),rgba(6,182,212,.15));
    color:#a78bfa;
    box-shadow:0 0 16px rgba(124,58,237,.2);
}
.nav-btn.active::before {
    content:'';
    position:absolute;right:-1px;
    top:50%;transform:translateY(-50%);
    width:3px;height:28px;
    background:linear-gradient(180deg,#7c3aed,#06b6d4);
    border-radius:3px 0 0 3px;
}
.nav-tooltip {
    position:absolute;left:60px;
    background:#1e1b4b;
    color:#c4b5fd;
    font-size:.7rem;font-weight:600;
    padding:5px 10px;
    border-radius:7px;
    white-space:nowrap;
    pointer-events:none;
    opacity:0;
    transition:opacity .15s;
    border:1px solid rgba(139,92,246,.2);
}
.nav-btn:hover .nav-tooltip { opacity:1; }

/* ─── Page canvas ───────────────────────────────────────────────────────── */
.page-canvas {
    margin-left:72px;
    padding:28px 32px 48px;
    min-height:100vh;
    max-width:1400px;
}

/* ─── Page header ───────────────────────────────────────────────────────── */
.pg-header {
    display:flex;
    align-items:flex-end;
    gap:16px;
    margin-bottom:28px;
    padding-bottom:20px;
    border-bottom:1px solid rgba(139,92,246,.1);
}
.pg-icon {
    width:52px;height:52px;
    border-radius:16px;
    background:linear-gradient(135deg,rgba(124,58,237,.2),rgba(6,182,212,.1));
    border:1px solid rgba(139,92,246,.25);
    display:flex;align-items:center;justify-content:center;
    font-size:1.5rem;
    flex-shrink:0;
}
.pg-title { font-size:1.6rem;font-weight:800;color:#f1f5f9;line-height:1; }
.pg-sub { font-size:.8rem;color:#475569;margin-top:4px; }

/* ─── Stat cards ─────────────────────────────────────────────────────────── */
.stat-row { display:grid;gap:16px;margin-bottom:24px; }
.stat-card {
    background:#0d1021;
    border:1px solid rgba(139,92,246,.12);
    border-radius:16px;
    padding:20px 22px;
    transition:all .25s;
    position:relative;
    overflow:hidden;
}
.stat-card::after {
    content:'';
    position:absolute;inset:0;
    background:linear-gradient(135deg,rgba(124,58,237,.04),transparent 60%);
    pointer-events:none;
}
.stat-card:hover { border-color:rgba(139,92,246,.3); transform:translateY(-2px); box-shadow:0 8px 32px rgba(124,58,237,.12); }
.stat-label { font-size:.7rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:#374151;margin-bottom:8px; }
.stat-val { font-size:2rem;font-weight:800;background:linear-gradient(135deg,#a78bfa,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1; }
.stat-delta { font-size:.75rem;color:#10b981;margin-top:6px; }

/* ─── Glass card ─────────────────────────────────────────────────────────── */
.gcard {
    background:rgba(13,16,33,.85);
    backdrop-filter:blur(20px);
    border:1px solid rgba(139,92,246,.1);
    border-radius:18px;
    padding:22px 26px;
    margin-bottom:16px;
}
.gcard-title { font-size:.95rem;font-weight:700;color:#e2e8f0;margin-bottom:12px; }

/* ─── Pipeline steps ────────────────────────────────────────────────────── */
.pipe-step {
    display:flex;
    align-items:center;
    gap:16px;
    padding:16px 20px;
    background:#0d1021;
    border:1px solid rgba(139,92,246,.1);
    border-radius:14px;
    margin-bottom:8px;
    transition:all .3s;
    position:relative;overflow:hidden;
}
.pipe-step.active {
    border-color:rgba(124,58,237,.5);
    background:linear-gradient(135deg,rgba(124,58,237,.1),rgba(13,16,33,1));
    box-shadow:0 0 32px rgba(124,58,237,.15);
}
.pipe-step.active::before {
    content:'';position:absolute;left:0;top:0;bottom:0;
    width:3px;
    background:linear-gradient(180deg,#7c3aed,#06b6d4);
}
.pipe-step.done { border-color:rgba(16,185,129,.2); }
.pipe-icon { font-size:1.6rem;width:40px;text-align:center;flex-shrink:0; }
.pipe-name { font-weight:700;font-size:.95rem;color:#e2e8f0; }
.pipe-name.a { color:#a78bfa; }
.pipe-desc { font-size:.78rem;color:#374151;margin-top:2px; }
.live-dot {
    width:8px;height:8px;border-radius:50%;
    background:#a78bfa;
    box-shadow:0 0 8px #7c3aed;
    animation:blink 1.2s infinite;
    margin-left:auto;flex-shrink:0;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

/* ─── Pill badge ─────────────────────────────────────────────────────────── */
.pill {
    display:inline-flex;align-items:center;gap:5px;
    padding:3px 11px;border-radius:20px;
    font-size:.7rem;font-weight:700;letter-spacing:.04em;
}
.pill-v { background:rgba(16,185,129,.12);color:#34d399;border:1px solid rgba(16,185,129,.25); }
.pill-w { background:rgba(245,158,11,.12);color:#fbbf24;border:1px solid rgba(245,158,11,.25); }
.pill-i { background:rgba(139,92,246,.12);color:#a78bfa;border:1px solid rgba(139,92,246,.25); }
.pill-e { background:rgba(239,68,68,.12);color:#f87171;border:1px solid rgba(239,68,68,.25); }

/* ─── Input overrides ───────────────────────────────────────────────────── */
.stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
    background:#0d1021 !important;
    border:1px solid rgba(139,92,246,.2) !important;
    border-radius:10px !important;
    color:#e2e8f0 !important;
    font-family:'Inter',sans-serif !important;
    font-size:.9rem !important;
}
.stTextInput input:focus { border-color:#7c3aed !important; box-shadow:0 0 0 3px rgba(124,58,237,.15) !important; }
.stSlider [data-baseweb="slider"] { margin-top:8px; }

/* ─── Button overrides ───────────────────────────────────────────────────── */
.stButton > button {
    background:linear-gradient(135deg,#7c3aed,#5b21b6) !important;
    color:#fff !important;border:none !important;
    border-radius:11px !important;
    padding:.6rem 1.6rem !important;
    font-weight:700 !important;font-size:.88rem !important;
    letter-spacing:.01em;
    transition:all .2s !important;
    font-family:'Inter',sans-serif !important;
}
.stButton > button:hover {
    background:linear-gradient(135deg,#6d28d9,#4c1d95) !important;
    transform:translateY(-1px) !important;
    box-shadow:0 8px 24px rgba(124,58,237,.35) !important;
}

/* ─── Metric overrides ───────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background:#0d1021;
    border:1px solid rgba(139,92,246,.12);
    border-radius:14px;
    padding:18px 20px !important;
}
[data-testid="stMetricValue"] { color:#a78bfa !important; font-weight:800; }
[data-testid="stMetricLabel"] { color:#374151 !important; font-size:.72rem !important; text-transform:uppercase;letter-spacing:.08em; }

/* ─── Alerts ─────────────────────────────────────────────────────────────── */
.stAlert { border-radius:12px !important; border-left-width:3px !important; }
div[data-testid="stInfo"] { background:rgba(139,92,246,.08) !important; border-color:#7c3aed !important; }
div[data-testid="stWarning"] { background:rgba(245,158,11,.08) !important; border-color:#f59e0b !important; }
div[data-testid="stSuccess"] { background:rgba(16,185,129,.08) !important; border-color:#10b981 !important; }
div[data-testid="stError"] { background:rgba(239,68,68,.08) !important; border-color:#ef4444 !important; }

/* ─── Code ───────────────────────────────────────────────────────────────── */
code, .stCode { background:#0a0d1f !important; border:1px solid rgba(139,92,246,.18) !important; border-radius:8px !important; color:#c4b5fd !important; font-family:'JetBrains Mono',monospace !important; }

/* ─── Toggle ─────────────────────────────────────────────────────────────── */
.stToggle span { font-size:.85rem !important; color:#94a3b8 !important; }

/* ─── Divider ─────────────────────────────────────────────────────────────── */
.vdiv { height:1px;background:linear-gradient(90deg,transparent,rgba(139,92,246,.3),transparent);margin:20px 0; }

/* ─── Paper card (literature) ────────────────────────────────────────────── */
.paper-card {
    background:#0d1021;
    border:1px solid rgba(139,92,246,.1);
    border-radius:14px;
    padding:18px 20px;
    margin-bottom:10px;
    transition:all .2s;
}
.paper-card:hover { border-color:rgba(139,92,246,.3); box-shadow:0 4px 20px rgba(124,58,237,.1); }
.paper-title { font-weight:700;font-size:.95rem;color:#c4b5fd;margin-bottom:4px; }
.paper-meta { font-size:.74rem;color:#374151;margin-bottom:8px; }
.paper-snippet { font-size:.82rem;color:#64748b;line-height:1.55; }

/* ─── Animate in ─────────────────────────────────────────────────────────── */
@keyframes fadeUp { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
.fade-up { animation:fadeUp .35s ease forwards; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAV (icon rail)
# ════════════════════════════════════════════════════════════════════════════
PAGES = [
    ("🧪", "Discovery Studio"),
    ("🌳", "Agent Pipeline"),
    ("📚", "Literature"),
    ("📄", "Paper Viewer"),
    ("💰", "Cost Analytics"),
    ("📊", "Benchmark"),
]

with st.sidebar:
    st.markdown("""
    <div class="nav-logo">🔬</div>
    <div class="nav-divider"></div>
    """, unsafe_allow_html=True)

    page_idx = st.radio(
        "nav",
        options=list(range(len(PAGES))),
        format_func=lambda i: PAGES[i][0],
        label_visibility="collapsed",
    )

page = PAGES[page_idx][1]

# ════════════════════════════════════════════════════════════════════════════
# PAGE HEADER HELPER
# ════════════════════════════════════════════════════════════════════════════
def page_header(icon, title, sub=""):
    st.markdown(f"""
    <div class="pg-header fade-up">
        <div class="pg-icon">{icon}</div>
        <div>
            <div class="pg-title">{title}</div>
            {"<div class='pg-sub'>"+sub+"</div>" if sub else ""}
        </div>
    </div>
    """, unsafe_allow_html=True)

def divider():
    st.markdown('<div class="vdiv"></div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# PAGE: DISCOVERY STUDIO
# ════════════════════════════════════════════════════════════════════════════
if page == "Discovery Studio":
    page_header("🧪", "Discovery Studio")

    left, right = st.columns([3, 2], gap="large")

    with left:
        topic = st.text_input(
            "Topic",
            placeholder="e.g. Sparse Transformers for genomics, CRISPR gene editing…",
            label_visibility="collapsed",
        )
        c1, c2 = st.columns(2)
        with c1:
            enable_critic = st.toggle("Statistical Critic", value=True)
        with c2:
            synth_latex  = st.toggle("Synthesize Paper", value=False)

        run_btn = st.button("⚡ Run Discovery", use_container_width=True)

        if run_btn:
            if not topic.strip():
                st.warning("Enter a research topic first.")
            else:
                if "run_state" not in st.session_state:
                    st.session_state.run_state = {}
                    st.session_state.active_agent = None
                try:
                    from src.orchestrator import build_orchestrator
                    graph = build_orchestrator(enable_critic=enable_critic)
                    with st.status("Running pipeline…", expanded=True) as status:
                        for event in graph.stream(
                            {"research_topic": topic.strip(), "enable_critic": enable_critic},
                            stream_mode="updates",
                        ):
                            for node_name, update in event.items():
                                st.session_state.run_state.update(update)
                                st.session_state.active_agent = node_name.replace("_"," ").title()
                                status.write(f"**{st.session_state.active_agent}**")
                        status.update(label="✅ Complete", state="complete")
                except Exception as exc:
                    st.error(f"{exc}")

    with right:
        run = getattr(st.session_state, "run_state", {})
        active = getattr(st.session_state, "active_agent", None) or "—"
        status_val  = run.get("execution_status", "Idle")
        retries     = run.get("retry_count", 0)
        verdict     = run.get("critic_verdict", "—")
        v_color     = "#34d399" if verdict == "ACCEPTED" else "#fbbf24"

        st.markdown(f"""
        <div class="gcard fade-up">
            <div class="gcard-title">Run Monitor</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
                <div>
                    <div class="stat-label">Active Agent</div>
                    <div style="font-weight:700;color:#a78bfa;font-size:.95rem;">{active}</div>
                </div>
                <div>
                    <div class="stat-label">Status</div>
                    <div style="font-weight:700;color:#e2e8f0;font-size:.95rem;">{status_val}</div>
                </div>
                <div>
                    <div class="stat-label">Retries</div>
                    <div style="font-weight:700;color:#e2e8f0;font-size:.95rem;">{retries}</div>
                </div>
                <div>
                    <div class="stat-label">Critic</div>
                    <div style="font-weight:700;color:{v_color};font-size:.95rem;">{verdict}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if run.get("selected_hypothesis"):
            st.markdown(f"""
            <div class="gcard fade-up" style="border-color:rgba(124,58,237,.25);">
                <div class="stat-label" style="margin-bottom:8px;">Hypothesis</div>
                <div style="font-style:italic;color:#c4b5fd;font-size:.88rem;line-height:1.6;">"{run['selected_hypothesis']}"</div>
            </div>
            """, unsafe_allow_html=True)

        if run.get("execution_result"):
            with st.expander("Execution Output"):
                st.code(run["execution_result"], language="text")


# ════════════════════════════════════════════════════════════════════════════
# PAGE: AGENT PIPELINE
# ════════════════════════════════════════════════════════════════════════════
elif page == "Agent Pipeline":
    page_header("🌳", "Agent Pipeline")

    active_agent = getattr(st.session_state, "active_agent", None)

    META = {
        "Literature Reviewer":  ("📚", "Retrieves & indexes relevant papers"),
        "Hypothesis Generator": ("💡", "Formulates novel, testable hypotheses"),
        "Code Executor":        ("⚙️", "Writes & runs sandboxed experiments"),
        "Debugger Node":        ("🔧", "Auto-fixes code failures"),
        "Critic Node":          ("🎓", "Statistical validation — p-value & Cohen's d"),
        "LaTeX Synthesizer":    ("📝", "Compiles publication-ready manuscript"),
    }

    if not active_agent:
        st.markdown("""
        <div class="gcard" style="text-align:center;padding:3rem;color:#374151;">
            <div style="font-size:2rem;margin-bottom:.5rem;">🚀</div>
            Start a run in Discovery Studio to watch agents activate here.
        </div>
        """, unsafe_allow_html=True)

    for i, agent in enumerate(AGENTS):
        emoji, desc = META[agent]
        is_active = agent == active_agent
        a_cls  = "active" if is_active else ""
        n_cls  = "a" if is_active else ""
        dot    = '<div class="live-dot"></div>' if is_active else ""
        st.markdown(f"""
        <div class="pipe-step {a_cls}">
            <div class="pipe-icon">{emoji}</div>
            <div style="flex:1;">
                <div class="pipe-name {n_cls}">{agent}</div>
                <div class="pipe-desc">{desc}</div>
            </div>
            {dot}
        </div>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# PAGE: LITERATURE
# ════════════════════════════════════════════════════════════════════════════
elif page == "Literature":
    page_header("📚", "Literature Search")

    c1, c2 = st.columns([5, 1], gap="small")
    with c1:
        query = st.text_input("q", placeholder="Search indexed papers…", label_visibility="collapsed")
    with c2:
        top_k = st.number_input("K", min_value=1, max_value=20, value=5, label_visibility="collapsed")

    min_score = st.slider("Min similarity", 0.0, 0.5, 0.0, 0.05, format="%.2f")

    if st.button("Search", disabled=not (query or "").strip()):
        try:
            from src.rag.retriever import get_relevant_literature
            with st.spinner("Searching…"):
                papers = get_relevant_literature(query, top_k=top_k, min_score=min_score)

            if not papers:
                st.info("No results. Try a broader query.")
            else:
                st.markdown(f'<p style="color:#374151;font-size:.8rem;margin-bottom:12px;">{len(papers)} result{"s" if len(papers)!=1 else ""}</p>', unsafe_allow_html=True)
                for p in papers:
                    title   = p.get("title") or p.get("paper_id", "Untitled")
                    authors = ", ".join(p.get("authors") or []) or "Unknown authors"
                    year    = p.get("year", "")
                    source  = p.get("source", "")
                    snippet = p.get("snippet", "")
                    sim     = p.get("similarity", "")
                    url     = p.get("url", "")
                    sim_str = f"{float(sim)*100:.0f}%" if isinstance(sim,(float,int)) else ""

                    st.markdown(f"""
                    <div class="paper-card fade-up">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <div class="paper-title">{title}</div>
                            {"<span class='pill pill-i'>"+sim_str+"</span>" if sim_str else ""}
                        </div>
                        <div class="paper-meta">{authors}{" · " + str(year) if year else ""}{" · " + source if source else ""}</div>
                        <div class="paper-snippet">{snippet[:280]}{"…" if len(snippet)>280 else ""}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if url:
                        st.link_button("Open →", url)
        except Exception as e:
            st.error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# PAGE: PAPER VIEWER
# ════════════════════════════════════════════════════════════════════════════
elif page == "Paper Viewer":
    page_header("📄", "Paper Viewer")
    render_paper_viewer()


# ════════════════════════════════════════════════════════════════════════════
# PAGE: COST ANALYTICS
# ════════════════════════════════════════════════════════════════════════════
elif page == "Cost Analytics":
    page_header("💰", "Cost Analytics")
    try:
        import plotly.io as pio
        pio.templates.default = "plotly_dark"
        from components.cost_analytics import render_cost_analytics
        render_cost_analytics()
    except Exception as e:
        st.error(str(e))


# ════════════════════════════════════════════════════════════════════════════
# PAGE: BENCHMARK
# ════════════════════════════════════════════════════════════════════════════
elif page == "Benchmark":
    page_header("📊", "Holdout Benchmark")

    st.markdown("""
    <div class="stat-row" style="grid-template-columns:repeat(4,1fr);">
        <div class="stat-card">
            <div class="stat-label">Papers</div>
            <div class="stat-val">9</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Dimensions</div>
            <div class="stat-val">4</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Domains</div>
            <div class="stat-val">3</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Max Score</div>
            <div class="stat-val">10</div>
        </div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:24px;">
        <span class="pill pill-i">🤖 AI / ML</span>
        <span class="pill pill-v">🧬 Comp. Biology</span>
        <span class="pill pill-w">⚛️ Physics</span>
    </div>
    """, unsafe_allow_html=True)

    radar = Path("docs/figures/benchmark_radar.svg")
    if radar.exists():
        _, mid, _ = st.columns([1, 2, 1])
        with mid:
            st.image(str(radar))
    else:
        st.markdown('<div class="gcard" style="text-align:center;color:#374151;">Radar chart not found at <code>docs/figures/benchmark_radar.svg</code></div>', unsafe_allow_html=True)

    report = Path("docs/evaluation_benchmark_report.md")
    if report.exists():
        divider()
        st.markdown(report.read_text(encoding="utf-8"))
