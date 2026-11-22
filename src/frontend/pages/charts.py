import json

import streamlit as st

from src.frontend import components as ui
from src.frontend.services import charts as chart_service
from src.frontend.utils import state
from src.frontend.utils.env import vision_status
from src.frontend.utils.files import save_upload, validate_upload

state.init_state()
ui.page_header("Chart Interpretation", "Week 3: read scientific charts with a vision-language model.")
vision = vision_status()
if not vision["configured"]:
    st.warning(f"Vision model not configured. {vision.get('problem') or ''} The model must be vision-capable.")

files = st.file_uploader("Upload chart images (PNG, JPG, GIF, WebP, up to 5 MB each)",
                         type=["png", "jpg", "jpeg", "gif", "webp"], accept_multiple_files=True, key="chart_upload")
valid = []
for f in files or []:
    data = f.getvalue()
    error = validate_upload(f.name, data, (".png", ".jpg", ".jpeg", ".gif", ".webp"), 5)
    if error:
        st.error(error)
    else:
        valid.append((f.name, data))
if valid:
    cols = st.columns(min(len(valid), 4))
    for col, (name, data) in zip(cols, valid):
        try:
            col.image(data, caption=name, width="stretch")
        except Exception:  # corrupt file with an image extension: the reader will report it clearly
            col.warning(f"No preview available for {name} (it may not be a valid image).")

if st.button("Read charts", type="primary", disabled=not (valid and vision["configured"])):
    progress = st.progress(0.0, text="Reading charts...")
    for i, (name, data) in enumerate(valid):
        res = chart_service.read_chart(data, name)
        path = save_upload(data, name, state.OUTPUT_DIR / "charts")
        if not any(c["path"] == str(path) for c in st.session_state["chart_images"]):
            st.session_state["chart_images"].append({"name": name, "path": str(path)})
        state.add_upload("chart", name, len(data))
        entry = {"name": name, "ok": res.ok, "seconds": round(res.seconds, 1), "path": str(path)}
        entry.update({"data": res.data} if res.ok else {"message": res.message})
        st.session_state["chart_results"] = [c for c in st.session_state["chart_results"] if c["name"] != name] + [entry]
        state.add_trace(f"Chart: {name}", "ok" if res.ok else "error", res.seconds, res.message, vision["model"] or "")
        progress.progress((i + 1) / len(valid), text=f"Read {i + 1} of {len(valid)}")
    progress.empty()

for entry in st.session_state["chart_results"]:
    st.divider()
    st.subheader(entry["name"])
    if not entry["ok"]:
        st.error(entry["message"])
        continue
    ex = entry["data"]
    st.markdown(chart_service.explanation(ex))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Baseline values**")
        if ex["baseline_values"]:
            st.dataframe(ex["baseline_values"], width="stretch", hide_index=True)
        else:
            st.caption("None reported by the model.")
        st.markdown("**Peak performance**")
        st.json(ex["peak_performance"]) if ex["peak_performance"] else st.caption("None reported by the model.")
    with c2:
        df = chart_service.points_dataframe(ex)
        st.markdown("**Extracted data points** (observed / estimated as labelled)")
        if df.empty:
            st.caption("No readable data points.")
        else:
            st.dataframe(df, width="stretch", hide_index=True)
            numeric = df.assign(x=df["x"].apply(lambda v: v if isinstance(v, (int, float)) else None)).dropna(subset=["x"])
            if not numeric.empty:
                st.scatter_chart(numeric, x="x", y="y", color="series")
    with st.expander("Raw JSON"):
        st.json(ex)
    st.download_button("Download extraction (JSON)", json.dumps(ex, indent=2), file_name=f"{entry['name']}.extraction.json",
                       mime="application/json", key=f"dl_{entry['name']}")
