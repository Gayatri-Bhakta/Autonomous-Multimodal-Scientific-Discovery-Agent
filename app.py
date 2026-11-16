"""Streamlit entry point: python -m streamlit run app.py

A thin router. All backend access goes through src/frontend/services/."""
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="Scientific Discovery Agent", page_icon="🔬", layout="wide")

from src.frontend import components as ui  # noqa: E402
from src.frontend.services.status import environment_status  # noqa: E402
from src.frontend.theme import apply_theme  # noqa: E402
from src.frontend.utils import state  # noqa: E402
from src.frontend.utils.env import load_environment  # noqa: E402

load_environment()
state.init_state()
apply_theme()

PROJECT_ROOT = Path(__file__).resolve().parent

PAGES = [
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/home.py"), title="Home Dashboard", icon="🏠", default=True),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/literature.py"), title="Literature Review", icon="📚"),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/hypothesis.py"), title="Hypothesis Generation", icon="💡"),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/charts.py"), title="Chart Interpretation", icon="📈"),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/experiment.py"), title="Experiment / Code Execution", icon="🧪"),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/paper.py"), title="Research Paper Generation", icon="📝"),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/reports.py"), title="Results and Reports", icon="📦"),
    st.Page(str(PROJECT_ROOT / "src/frontend/pages/about.py"), title="About Project", icon="ℹ️"),
]
navigation = st.navigation(PAGES)

env = environment_status()
with st.sidebar:
    st.markdown("### 🔬 Discovery Agent")
    st.caption("Autonomous Multimodal Scientific Discovery Agent")
    st.markdown(f"LLM {ui.badge('ready' if env['llm']['configured'] else 'needs_config')}<br>"
                f"Vision {ui.badge('ready' if env['vision']['configured'] else 'needs_config')}<br>"
                f"LaTeX {ui.badge('ready' if env['latex']['available'] else 'needs_config')}", unsafe_allow_html=True)
    st.caption("API keys are read from the environment and are never displayed.")

navigation.run()
