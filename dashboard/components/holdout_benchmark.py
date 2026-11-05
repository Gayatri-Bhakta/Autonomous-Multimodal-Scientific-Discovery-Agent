import csv
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RADAR_CANDIDATES = (
    PROJECT_ROOT / "dashboard" / "assets" / "benchmark_radar.svg",
    PROJECT_ROOT / "data" / "benchmark_radar.svg",
)
TABLE_CANDIDATES = (
    PROJECT_ROOT / "data" / "holdout_benchmark.csv",
    PROJECT_ROOT / "data" / "benchmark_comparison.csv",
)


def render_holdout_benchmark() -> None:
    """Show Afrah's radar chart and the holdout comparison table when present."""
    st.header("Holdout Benchmark")
    st.caption("Compare the system's holdout evaluation against the benchmark results.")

    radar_path = next((path for path in RADAR_CANDIDATES if path.is_file()), None)
    table_path = next((path for path in TABLE_CANDIDATES if path.is_file()), None)

    if radar_path:
        with st.container(border=True):
            st.subheader("Benchmark radar")
            st.image(radar_path.read_bytes(), use_container_width=True)
            st.caption(f"Source: {radar_path.name}")
    else:
        st.info(
            "Afrah's `benchmark_radar.svg` is not in this checkout yet. "
            "Place it in `dashboard/assets/` or `data/` to show it here."
        )

    if table_path:
        with table_path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        if rows:
            with st.container(border=True):
                st.subheader("Comparison results")
                st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.warning(f"The comparison table is empty: {table_path.name}")
    else:
        st.info(
            "The holdout comparison table is not available yet. "
            "Add Afrah's results as `data/holdout_benchmark.csv` to display the table."
        )
