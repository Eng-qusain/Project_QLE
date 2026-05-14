"""
app.py  –  Project_QLE Streamlit Dashboard
───────────────────────────────────────────
Libya Petroleum Exploration Interpretation Platform

Run:
    streamlit run app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import io
import tempfile
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy import stats
import streamlit as st

# ─── Page config (MUST be first Streamlit call) ─────────────────
st.set_page_config(
    page_title    = "Project_QLE",
    page_icon     = "🛢️",
    layout        = "wide",
    initial_sidebar_state = "expanded",
)

# ─── CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { background: #0d1b2a; }
  [data-testid="stSidebar"] * { color: #e0e8f0 !important; }
  .block-container { padding-top: 1.2rem; }
  .metric-card {
    background: linear-gradient(135deg,#0d1b2a,#1a3550);
    border: 1px solid #2a5080; border-radius:10px;
    padding:18px 20px; text-align:center; margin:4px 0;
  }
  .metric-card .label { font-size:.78rem; color:#8ab4d4; letter-spacing:.06em; text-transform:uppercase; }
  .metric-card .value { font-size:1.7rem; font-weight:700; color:#4fc3f7; margin-top:4px; }
  .metric-card .sub   { font-size:.72rem; color:#607d8b; margin-top:2px; }
  .section-header {
    border-left:4px solid #4fc3f7; padding-left:12px;
    font-size:1.1rem; font-weight:600; color:#e0e8f0; margin:18px 0 10px;
  }
  .gemini-box {
    background:#0a1628; border:1px solid #1e4060;
    border-radius:8px; padding:16px 20px;
    font-size:.88rem; line-height:1.7; color:#cdd8e3;
  }
  .risk-low    { background:#1b3a1b; color:#81c784; border:1px solid #388e3c;
                 border-radius:6px; padding:4px 12px; font-weight:700; }
  .risk-mod    { background:#3a2d0a; color:#ffb74d; border:1px solid #f57c00;
                 border-radius:6px; padding:4px 12px; font-weight:700; }
  .risk-high   { background:#3a1010; color:#ef9a9a; border:1px solid #c62828;
                 border-radius:6px; padding:4px 12px; font-weight:700; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════
#  SESSION STATE HELPERS
# ════════════════════════════════════════════

def ss(key, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


# ════════════════════════════════════════════
#  LAZY IMPORTS (only when modules available)
# ════════════════════════════════════════════

@st.cache_resource
def _check_deps():
    missing = []
    for pkg, pip in [
        ("lasio",      "lasio"),
        ("sklearn",    "scikit-learn"),
        ("scipy",      "scipy"),
    ]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pip)
    return missing


# ════════════════════════════════════════════
#  WELL LOG PARSING
# ════════════════════════════════════════════

def parse_uploaded_las(uploaded_file, basin: str):
    """Parse a Streamlit UploadedFile as LAS."""
    try:
        import lasio
        with tempfile.NamedTemporaryFile(suffix=".las", delete=False) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        from Project_QLE.parsers import parse_las
        well = parse_las(tmp_path)
        well.header.basin = basin
        os.unlink(tmp_path)
        return well, None
    except Exception as e:
        return None, str(e)


# ════════════════════════════════════════════
#  PLOTTING HELPERS
# ════════════════════════════════════════════

TRACK_COLORS = {
    "GR"      : "#4caf50",
    "RHOB"    : "#e91e63",
    "NPHI"    : "#2196f3",
    "RT"      : "#ff9800",
    "DT"      : "#9c27b0",
    "VSHALE"  : "#795548",
    "PHIE"    : "#00bcd4",
    "SW"      : "#3f51b5",
    "PERM_mD" : "#f44336",
    "FACIES"  : "#607d8b",
    "PORE_PRESS_PSI": "#ff5722",
}

FACIES_COLORS = {
    "Sandstone" : "#f9a825",
    "Shale"     : "#546e7a",
    "Limestone" : "#80cbc4",
    "Dolomite"  : "#a5d6a7",
    "Anhydrite" : "#ce93d8",
    "Unknown"   : "#37474f",
}

LOG_SCALES = {
    "RT": "log",
    "PERM_mD": "log",
}


def make_log_plot(df: pd.DataFrame, curves: list,
                  depth_col: str = "DEPTH",
                  title: str = "") -> plt.Figure:
    """Multi-track well log plot."""
    if depth_col not in df.columns:
        depth_col = "DEPT" if "DEPT" in df.columns else df.columns[0]

    depth = df[depth_col].values
    available = [c for c in curves if c in df.columns and c != depth_col]
    if not available:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No curves to display", ha="center", va="center")
        return fig

    n = len(available)
    fig, axes = plt.subplots(1, n, figsize=(2.8 * n, 10), sharey=True)
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor("#0d1b2a")

    for ax, curve in zip(axes, available):
        ax.set_facecolor("#111d2b")
        vals = df[curve].values.astype(float)
        valid = ~np.isnan(vals)

        color = TRACK_COLORS.get(curve, "#78909c")
        scale = LOG_SCALES.get(curve, "linear")

        if scale == "log":
            vals_plot = np.where(vals > 0, vals, np.nan)
            ax.semilogx(vals_plot, depth, color=color, lw=0.8)
            ax.fill_betweenx(depth, np.nanmin(vals_plot[valid & (vals_plot > 0)]),
                              vals_plot, alpha=0.25, color=color)
        else:
            ax.plot(vals, depth, color=color, lw=0.8)
            p2, p98 = np.nanpercentile(vals[valid], [2, 98]) if valid.any() else (0, 1)
            ax.fill_betweenx(depth, p2, vals, where=(vals >= p2),
                              alpha=0.25, color=color)
            ax.set_xlim(p2 - (p98 - p2) * 0.05, p98 + (p98 - p2) * 0.05)

        ax.set_xlabel(curve, color=color, fontsize=8, fontweight="bold")
        ax.tick_params(colors="#8ab4d4", labelsize=6)
        ax.spines[:].set_color("#1e3a5a")
        ax.grid(axis="y", color="#1e3a5a", lw=0.4, alpha=0.6)
        ax.invert_yaxis()

    axes[0].set_ylabel("Depth (m)", color="#8ab4d4", fontsize=8)
    axes[0].tick_params(axis="y", colors="#8ab4d4")

    if title:
        fig.suptitle(title, color="#4fc3f7", fontsize=10, fontweight="bold", y=1.01)

    plt.tight_layout(w_pad=0.1)
    return fig


def make_facies_track(depth: np.ndarray, facies: np.ndarray) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(1.2, 10))
    fig.patch.set_facecolor("#0d1b2a")
    ax.set_facecolor("#111d2b")

    unique = np.unique(facies)
    for i in range(len(depth) - 1):
        color = FACIES_COLORS.get(facies[i], "#37474f")
        ax.fill_betweenx([depth[i], depth[i+1]], 0, 1, color=color, alpha=0.9)

    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_xlabel("Facies", color="#8ab4d4", fontsize=8)
    ax.tick_params(colors="#8ab4d4", labelsize=6)
    ax.spines[:].set_color("#1e3a5a")
    ax.invert_yaxis()
    plt.tight_layout()
    return fig


def make_crossplot(df: pd.DataFrame, x_col: str, y_col: str,
                   color_col: str = "VSHALE",
                   title: str = "") -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor("#0d1b2a")
    ax.set_facecolor("#111d2b")

    mask = df[[x_col, y_col]].notna().all(axis=1)
    x = df.loc[mask, x_col].values
    y = df.loc[mask, y_col].values

    c = None
    if color_col in df.columns:
        c = df.loc[mask, color_col].values

    sc = ax.scatter(x, y, c=c, cmap="RdYlGn_r" if c is not None else None,
                    s=4, alpha=0.6, linewidths=0)
    if c is not None:
        cb = plt.colorbar(sc, ax=ax)
        cb.set_label(color_col, color="#8ab4d4", fontsize=8)
        cb.ax.tick_params(colors="#8ab4d4")

    ax.set_xlabel(x_col, color="#8ab4d4")
    ax.set_ylabel(y_col, color="#8ab4d4")
    ax.set_title(title or f"{x_col} vs {y_col}", color="#4fc3f7", fontsize=9)
    ax.tick_params(colors="#8ab4d4")
    ax.spines[:].set_color("#1e3a5a")
    ax.grid(color="#1e3a5a", lw=0.4, alpha=0.5)
    plt.tight_layout()
    return fig


def make_histogram(values: np.ndarray, title: str,
                   color: str = "#4fc3f7", units: str = "") -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    fig.patch.set_facecolor("#0d1b2a")
    ax.set_facecolor("#111d2b")
    clean = values[~np.isnan(values)]
    ax.hist(clean, bins=40, color=color, alpha=0.8, edgecolor="#0d1b2a", lw=0.4)
    for pct, ls in [(10, "--"), (50, "-"), (90, "--")]:
        val = np.percentile(clean, pct)
        ax.axvline(val, color="#ff9800", lw=1, ls=ls,
                   label=f"P{pct}={val:.2f}")
    ax.legend(fontsize=7, labelcolor="#8ab4d4", facecolor="#0d1b2a", edgecolor="#1e3a5a")
    ax.set_title(title, color="#4fc3f7", fontsize=9)
    ax.set_xlabel(units, color="#8ab4d4")
    ax.set_ylabel("Count", color="#8ab4d4")
    ax.tick_params(colors="#8ab4d4")
    ax.spines[:].set_color("#1e3a5a")
    plt.tight_layout()
    return fig


# ════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🛢️ Project_QLE")
    st.markdown("*Libya Exploration Platform*")
    st.divider()

    page = st.radio(
        "Navigation",
        ["🏠 Home",
         "📁 Data Upload",
         "📊 Well Log Viewer",
         "⚗️ Petrophysics",
         "🪨 Facies Analysis",
         "📈 Statistics",
         "🔗 Log Correlation",
         "🏭 Reservoir Summary",
         "🗺️ Map View",
         "🤖 AI Interpretation",
         "📋 Full Report"],
        label_visibility="collapsed",
    )
    st.divider()

    st.markdown("**Basin**")
    basin = st.selectbox(
        "Active Basin",
        ["SIRTE", "GHADAMES", "MURZUQ", "KUFRA", "OFFSHORE"],
        label_visibility="collapsed",
    )

    st.markdown("**Gemini API Key**")
    gemini_key = st.text_input(
        "Gemini Key",
        value=os.environ.get("GEMINI_API_KEY", ""),
        type="password",
        label_visibility="collapsed",
        placeholder="AIza…",
    )
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

    st.divider()
    st.caption("Project_QLE v1.0  |  Libya NOC")


# ════════════════════════════════════════════
#  HOME
# ════════════════════════════════════════════

if page == "🏠 Home":
    st.markdown("# 🛢️ Project_QLE")
    st.markdown("### Libya Petroleum Exploration Interpretation Platform")
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    wells = ss("wells", [])
    with col1:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Wells Loaded</div>
            <div class="value">{len(wells)}</div>
            <div class="sub">LAS files</div></div>""", unsafe_allow_html=True)
    with col2:
        reports = ss("report")
        n_res = len(reports.reservoirs) if reports else 0
        st.markdown(f"""<div class="metric-card">
            <div class="label">Reservoir Zones</div>
            <div class="value">{n_res}</div>
            <div class="sub">interpreted</div></div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""<div class="metric-card">
            <div class="label">Active Basin</div>
            <div class="value" style="font-size:1.2rem">{basin}</div>
            <div class="sub">Libya</div></div>""", unsafe_allow_html=True)
    with col4:
        ai_ready = bool(gemini_key)
        st.markdown(f"""<div class="metric-card">
            <div class="label">AI Engine</div>
            <div class="value" style="font-size:1rem;color:{'#4fc3f7' if ai_ready else '#607d8b'}">
                {'✓ Gemini' if ai_ready else '○ Not set'}</div>
            <div class="sub">Gemini 1.5</div></div>""", unsafe_allow_html=True)

    st.divider()

    st.markdown("#### Libyan Basins Overview")
    try:
        from Project_QLE.core.libya_geology import LIBYAN_FIELDS
        fields_df = pd.DataFrame(LIBYAN_FIELDS)
        col_a, col_b = st.columns([2, 1])
        with col_a:
            try:
                st.map(fields_df.rename(columns={"lat":"latitude","lon":"longitude"})[
                    ["latitude","longitude","name"]
                ], zoom=4, use_container_width=True)
            except Exception:
                st.dataframe(fields_df[["name","basin","fluid","api"]], use_container_width=True)
        with col_b:
            st.dataframe(
                fields_df[["name","basin","fluid","api"]].rename(
                    columns={"api":"API°","fluid":"Fluid"}),
                use_container_width=True, height=340,
            )
    except Exception as e:
        st.info(f"Install project dependencies to view field map: {e}")

    st.divider()
    st.markdown("#### Workflow")
    steps = [
        ("1","📁 Upload","LAS, SEGY, CSV, PDF"),
        ("2","⚗️ Petrophysics","Vshale, φ, Sw, Pressure"),
        ("3","🪨 Facies","Rule-based or ML clustering"),
        ("4","📈 Statistics","P10/P50/P90, correlations"),
        ("5","🏭 Reservoir","Net pay, FZI, OWC/GOC"),
        ("6","🤖 AI","Gemini narrative report"),
    ]
    cols = st.columns(6)
    for col, (n, title, desc) in zip(cols, steps):
        with col:
            st.markdown(f"""<div class="metric-card">
                <div class="value" style="font-size:1.3rem">{title}</div>
                <div class="sub" style="margin-top:6px">{desc}</div>
                </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════
#  DATA UPLOAD
# ════════════════════════════════════════════

elif page == "📁 Data Upload":
    st.markdown("## 📁 Data Upload")
    st.divider()

    missing = _check_deps()
    if missing:
        st.error(f"Missing packages: `{', '.join(missing)}`\n\nRun in terminal:\n```\npip install {' '.join(missing)}\n```")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-header">LAS Well Log Files</div>', unsafe_allow_html=True)
        uploaded_las = st.file_uploader(
            "Upload LAS files", type=["las"], accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded_las:
            if st.button("▶ Parse LAS Files", use_container_width=True):
                wells = []
                errs  = []
                prog  = st.progress(0, "Parsing …")
                for i, f in enumerate(uploaded_las):
                    prog.progress((i+1)/len(uploaded_las), f"Parsing {f.name} …")
                    well, err = parse_uploaded_las(f, basin)
                    if err:
                        errs.append(f"{f.name}: {err}")
                    else:
                        wells.append(well)
                st.session_state["wells"] = wells
                if errs:
                    for e in errs:
                        st.warning(e)
                if wells:
                    st.success(f"✓ Loaded {len(wells)} well(s)")

    with col2:
        st.markdown('<div class="section-header">Other Files (CSV, PDF, XML, JPG)</div>', unsafe_allow_html=True)
        uploaded_other = st.file_uploader(
            "Other files", type=["csv","pdf","xml","jpg","png","docx"],
            accept_multiple_files=True, label_visibility="collapsed",
        )
        if uploaded_other:
            for f in uploaded_other:
                if f.name.endswith(".csv"):
                    try:
                        df_csv = pd.read_csv(f)
                        st.success(f"✓ CSV: {f.name}  ({len(df_csv)} rows × {len(df_csv.columns)} cols)")
                        st.dataframe(df_csv.head(5), use_container_width=True)
                    except Exception as e:
                        st.warning(f"{f.name}: {e}")

    # Show loaded wells
    wells = ss("wells", [])
    if wells:
        st.divider()
        st.markdown("#### Loaded Wells")
        rows = []
        for w in wells:
            rows.append({
                "Well Name"   : w.header.well_name,
                "Basin"       : w.header.basin,
                "Start (m)"   : w.header.start_depth,
                "Stop (m)"    : w.header.stop_depth,
                "Step (m)"    : w.header.step,
                "Curves"      : ", ".join(list(w.curves.keys())[:10]) + ("…" if len(w.curves) > 10 else ""),
                "N Curves"    : len(w.curves),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ════════════════════════════════════════════
#  WELL LOG VIEWER
# ════════════════════════════════════════════

elif page == "📊 Well Log Viewer":
    st.markdown("## 📊 Well Log Viewer")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload LAS files in **📁 Data Upload** first.")
    else:
        well_names = [w.header.well_name for w in wells]
        chosen = st.selectbox("Select Well", well_names)
        well = next(w for w in wells if w.header.well_name == chosen)

        if well.df is None or well.df.empty:
            df_view = pd.DataFrame({c: well.curves[c].array for c in well.curves})
            df_view.insert(0, "DEPTH", well.get_depth())
        else:
            df_view = well.df.copy()

        raw_curves = [c for c in well.curves if c not in ("DEPT","DEPTH","MD")]
        derived    = [c for c in ["VSHALE","PHIE","PHID","SW","SHC","PERM_mD","PORE_PRESS_PSI"]
                      if c in df_view.columns]
        all_curves = raw_curves + [d for d in derived if d not in raw_curves]

        col1, col2 = st.columns([3, 1])
        with col2:
            st.markdown("**Select Tracks**")
            default_sel = [c for c in ["GR","RHOB","NPHI","RT"] if c in all_curves]
            selected = st.multiselect("Curves", all_curves, default=default_sel,
                                      label_visibility="collapsed")
            show_facies = "FACIES" in df_view.columns and st.checkbox("Show Facies Track", value=True)

            depth_col = "DEPTH" if "DEPTH" in df_view.columns else "DEPT"
            if depth_col in df_view.columns:
                d_min = float(df_view[depth_col].min())
                d_max = float(df_view[depth_col].max())
                d_range = st.slider("Depth Range (m)", d_min, d_max,
                                    (d_min, d_max), step=10.0)
                df_view = df_view[
                    (df_view[depth_col] >= d_range[0]) &
                    (df_view[depth_col] <= d_range[1])
                ]

        with col1:
            if selected:
                fig = make_log_plot(df_view, selected, depth_col,
                                    title=f"{chosen}  |  {well.header.basin} Basin")
                st.pyplot(fig, use_container_width=True)
            else:
                st.info("Select at least one curve →")

        if show_facies and "FACIES" in df_view.columns:
            depth_arr = df_view[depth_col].values
            facies_arr = df_view["FACIES"].values
            fig_f = make_facies_track(depth_arr, facies_arr)
            st.pyplot(fig_f)


# ════════════════════════════════════════════
#  PETROPHYSICS
# ════════════════════════════════════════════

elif page == "⚗️ Petrophysics":
    st.markdown("## ⚗️ Petrophysical Analysis")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload LAS files first.")
    else:
        col_cfg, col_res = st.columns([1, 3])

        with col_cfg:
            st.markdown("**Configuration**")
            chosen = st.selectbox("Well", [w.header.well_name for w in wells])
            well   = next(w for w in wells if w.header.well_name == chosen)
            sel_basin = st.selectbox("Basin Override",
                                      ["SIRTE","GHADAMES","MURZUQ","KUFRA"],
                                      index=["SIRTE","GHADAMES","MURZUQ","KUFRA"].index(
                                          well.header.basin if well.header.basin in
                                          ["SIRTE","GHADAMES","MURZUQ","KUFRA"] else "SIRTE"
                                      ))

            from Project_QLE.core.libya_geology import get_basin_defaults
            defs = get_basin_defaults(sel_basin)

            with st.expander("Advanced Parameters"):
                gr_clean   = st.number_input("GR Clean (GAPI)",  value=float(defs["gr_clean"]))
                gr_shale   = st.number_input("GR Shale (GAPI)",  value=float(defs["gr_shale"]))
                rho_matrix = st.number_input("ρ matrix (g/cc)",  value=float(defs["rho_matrix"]), step=0.01)
                rw         = st.number_input("Rw (ohm-m)",       value=float(defs["rw"]), step=0.001, format="%.3f")

            if st.button("▶ Run Petrophysics", use_container_width=True, type="primary"):
                with st.spinner("Computing …"):
                    try:
                        from Project_QLE.analysis import PetrophysicsEngine
                        eng = PetrophysicsEngine(
                            well, basin=sel_basin,
                            gr_clean=gr_clean, gr_shale=gr_shale,
                            rho_matrix=rho_matrix, rw=rw,
                        )
                        df_p = eng.run()
                        well.df = df_p
                        # Update in session
                        for i, w in enumerate(wells):
                            if w.header.well_name == chosen:
                                st.session_state["wells"][i] = well
                        st.session_state[f"petro_{chosen}"] = df_p
                        st.success("✓ Petrophysics complete")
                    except Exception as e:
                        st.error(str(e))

        with col_res:
            key = f"petro_{chosen}"
            if key not in st.session_state:
                st.info("Click **▶ Run Petrophysics** to compute.")
            else:
                df_p = st.session_state[key]

                # Metrics row
                metrics = {
                    "Avg PHIE": (f"{df_p['PHIE'].mean()*100:.1f}%"  if 'PHIE' in df_p.columns else "N/A", "Porosity"),
                    "Avg Sw":   (f"{df_p['SW'].mean()*100:.1f}%"    if 'SW'   in df_p.columns else "N/A", "Water Sat"),
                    "Avg Vsh":  (f"{df_p['VSHALE'].mean()*100:.1f}%"if 'VSHALE' in df_p.columns else "N/A","Vshale"),
                    "Avg k":    (f"{df_p['PERM_mD'].mean():.1f} mD" if 'PERM_mD' in df_p.columns else "N/A","Perm"),
                }
                cols = st.columns(4)
                for col, (label, (val, sub)) in zip(cols, metrics.items()):
                    with col:
                        st.markdown(f"""<div class="metric-card">
                            <div class="label">{label}</div>
                            <div class="value">{val}</div>
                            <div class="sub">{sub}</div></div>""",
                            unsafe_allow_html=True)

                tab1, tab2, tab3 = st.tabs(["📉 Log Tracks", "⬡ Crossplots", "📋 Data Table"])

                with tab1:
                    depth_col = "DEPTH" if "DEPTH" in df_p.columns else "DEPT"
                    derived = [c for c in ["GR","VSHALE","PHIE","SW","SHC","PERM_mD","PORE_PRESS_PSI"]
                               if c in df_p.columns]
                    fig = make_log_plot(df_p, derived, depth_col,
                                        title=f"{chosen} – Derived Curves")
                    st.pyplot(fig, use_container_width=True)

                with tab2:
                    c1, c2 = st.columns(2)
                    if "RHOB" in df_p.columns and "NPHI" in df_p.columns:
                        with c1:
                            st.pyplot(make_crossplot(df_p, "NPHI", "RHOB",
                                                     "VSHALE", "ND Crossplot"), use_container_width=True)
                    if "PHIE" in df_p.columns and "PERM_mD" in df_p.columns:
                        with c2:
                            st.pyplot(make_crossplot(df_p, "PHIE", "PERM_mD",
                                                     "SW", "Porosity–Perm"), use_container_width=True)

                with tab3:
                    show_cols = [c for c in df_p.columns if c not in ("DEPTH","DEPT")][:12]
                    st.dataframe(df_p[show_cols].round(4).head(200), use_container_width=True)
                    csv_bytes = df_p.to_csv(index=False).encode()
                    st.download_button("⬇ Download CSV", csv_bytes,
                                       f"{chosen}_petrophysics.csv", "text/csv")


# ════════════════════════════════════════════
#  FACIES ANALYSIS
# ════════════════════════════════════════════

elif page == "🪨 Facies Analysis":
    st.markdown("## 🪨 Facies Analysis")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload and process wells first.")
    else:
        col_cfg, col_out = st.columns([1, 3])
        with col_cfg:
            chosen = st.selectbox("Well", [w.header.well_name for w in wells])
            well   = next(w for w in wells if w.header.well_name == chosen)
            method = st.radio("Classification Method",
                              ["KMeans (Unsupervised)", "Rule-Based (GR/RHOB)"])
            n_clust = st.slider("KMeans Clusters", 3, 8, 5) if "KMeans" in method else 5

            if st.button("▶ Classify Facies", use_container_width=True, type="primary"):
                df_source = well.df if well.df is not None else pd.DataFrame(
                    {c: well.curves[c].array for c in well.curves}
                )
                if df_source.empty:
                    st.error("Run Petrophysics first for best results.")
                else:
                    from Project_QLE.analysis import KMeansFacies, RuleBasedFacies, labels_to_zones
                    try:
                        if "KMeans" in method:
                            labels = KMeansFacies(n_clusters=n_clust).fit_predict(df_source)
                        else:
                            labels = RuleBasedFacies().classify(df_source)
                        df_source["FACIES"] = labels
                        well.df = df_source
                        depth = well.get_depth()
                        zones = labels_to_zones(depth, labels) if depth is not None else []
                        st.session_state[f"facies_{chosen}"] = (labels, zones, df_source)
                        for i, w in enumerate(wells):
                            if w.header.well_name == chosen:
                                st.session_state["wells"][i] = well
                        st.success(f"✓ {len(zones)} zones identified")
                    except Exception as e:
                        st.error(str(e))

        with col_out:
            key = f"facies_{chosen}"
            if key not in st.session_state:
                st.info("Click **▶ Classify Facies**")
            else:
                labels, zones, df_f = st.session_state[key]
                unique, counts = np.unique(labels, return_counts=True)

                # Pie chart
                c1, c2 = st.columns(2)
                with c1:
                    fig, ax = plt.subplots(figsize=(4.5, 4.5))
                    fig.patch.set_facecolor("#0d1b2a")
                    ax.set_facecolor("#0d1b2a")
                    colors = [FACIES_COLORS.get(u, "#78909c") for u in unique]
                    ax.pie(counts, labels=unique, colors=colors,
                           autopct="%1.0f%%", startangle=90,
                           textprops={"color":"#e0e8f0","fontsize":8})
                    ax.set_title("Facies Distribution", color="#4fc3f7")
                    st.pyplot(fig, use_container_width=True)

                with c2:
                    depth = well.get_depth()
                    if depth is not None:
                        fig_f = make_facies_track(depth, labels)
                        st.pyplot(fig_f, use_container_width=True)

                st.markdown("**Zone Table**")
                zone_rows = [{"Top (m)": z.top, "Base (m)": z.base,
                               "Thickness (m)": round(z.base - z.top, 1),
                               "Facies": z.facies.value}
                              for z in zones]
                st.dataframe(pd.DataFrame(zone_rows), use_container_width=True)


# ════════════════════════════════════════════
#  STATISTICS
# ════════════════════════════════════════════

elif page == "📈 Statistics":
    st.markdown("## 📈 Statistical Analysis")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload wells first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)

        df_stat = well.df if (well.df is not None and not well.df.empty) else \
                  pd.DataFrame({c: well.curves[c].array for c in well.curves})

        numeric_cols = [c for c in df_stat.columns
                        if df_stat[c].dtype in [np.float64, np.float32, float]
                        and c not in ("DEPTH","DEPT","MD")]

        tab1, tab2, tab3, tab4 = st.tabs(
            ["📊 Descriptive", "📉 Histograms", "🔥 Correlation Matrix", "🎲 Monte Carlo"]
        )

        with tab1:
            from Project_QLE.analysis import batch_stats
            stats_list = batch_stats(well, numeric_cols[:12])
            if stats_list:
                rows = [{
                    "Curve": s.curve, "N": s.n,
                    "Mean": f"{s.mean:.3f}", "Std": f"{s.std:.3f}",
                    "Min": f"{s.min_val:.3f}", "Max": f"{s.max_val:.3f}",
                    "P10": f"{s.p10:.3f}", "P50": f"{s.p50:.3f}", "P90": f"{s.p90:.3f}",
                    "Skew": f"{s.skewness:.2f}",
                } for s in stats_list]
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

        with tab2:
            sel_hist = st.selectbox("Curve", numeric_cols)
            if sel_hist:
                vals = df_stat[sel_hist].values.astype(float)
                st.pyplot(make_histogram(vals, sel_hist, units=sel_hist))

        with tab3:
            from Project_QLE.analysis import pearson_matrix
            cross_cols = st.multiselect("Select curves",
                                         [c for c in numeric_cols if len(df_stat[c].dropna()) > 10],
                                         default=numeric_cols[:6])
            if cross_cols and len(cross_cols) >= 2:
                corr_mat = pearson_matrix(df_stat, cross_cols)
                fig, ax = plt.subplots(figsize=(7, 6))
                fig.patch.set_facecolor("#0d1b2a")
                ax.set_facecolor("#0d1b2a")
                im = ax.imshow(corr_mat.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
                ax.set_xticks(range(len(cross_cols))); ax.set_xticklabels(cross_cols, rotation=45, color="#8ab4d4", fontsize=8)
                ax.set_yticks(range(len(cross_cols))); ax.set_yticklabels(cross_cols, color="#8ab4d4", fontsize=8)
                for i in range(len(cross_cols)):
                    for j in range(len(cross_cols)):
                        ax.text(j, i, f"{corr_mat.values[i,j]:.2f}",
                                ha="center", va="center", fontsize=7, color="white")
                plt.colorbar(im, ax=ax)
                ax.set_title("Pearson Correlation Matrix", color="#4fc3f7")
                st.pyplot(fig, use_container_width=True)

        with tab4:
            from Project_QLE.analysis import monte_carlo_porosity
            st.markdown("**Monte Carlo Porosity Uncertainty**")
            c1, c2 = st.columns(2)
            phi_mean = c1.number_input("Mean porosity", 0.0, 0.5, 0.15, step=0.01)
            phi_std  = c2.number_input("Std dev", 0.001, 0.2, 0.04, step=0.005)
            n_mc = st.slider("Samples", 1000, 50000, 10000, step=1000)
            mc = monte_carlo_porosity(phi_mean, phi_std, n_mc)
            c1.metric("P10", f"{mc['p10']*100:.1f}%")
            c2.metric("P50", f"{mc['p50']*100:.1f}%")
            c1.metric("P90", f"{mc['p90']*100:.1f}%")
            edges = np.array(mc["histogram"]["edges"])
            counts= np.array(mc["histogram"]["counts"])
            fig, ax = plt.subplots(figsize=(5, 3))
            fig.patch.set_facecolor("#0d1b2a"); ax.set_facecolor("#111d2b")
            ax.bar(edges[:-1], counts, width=np.diff(edges), color="#4fc3f7", alpha=0.8)
            for p, v in [("P10",mc["p10"]),("P50",mc["p50"]),("P90",mc["p90"])]:
                ax.axvline(v, color="#ff9800", lw=1.5, ls="--", label=f"{p}={v*100:.1f}%")
            ax.legend(fontsize=8, labelcolor="#8ab4d4", facecolor="#0d1b2a")
            ax.set_xlabel("Porosity", color="#8ab4d4"); ax.set_ylabel("Count", color="#8ab4d4")
            ax.tick_params(colors="#8ab4d4"); ax.spines[:].set_color("#1e3a5a")
            ax.set_title("MC Porosity Distribution", color="#4fc3f7")
            st.pyplot(fig, use_container_width=True)


# ════════════════════════════════════════════
#  LOG CORRELATION
# ════════════════════════════════════════════

elif page == "🔗 Log Correlation":
    st.markdown("## 🔗 Cross-Well Log Correlation")
    wells = ss("wells", [])
    if len(wells) < 2:
        st.info("Load **2 or more wells** to run correlation.")
    else:
        curve = st.selectbox("Correlation Curve",
                              ["GR","RHOB","NPHI","RT","PHIE","SW"],
                              help="Curve used for cross-correlation")
        if st.button("▶ Correlate Wells", type="primary"):
            from Project_QLE.analysis import correlate_well_suite, correlate_markers_across_wells, pick_formation_tops
            with st.spinner("Correlating …"):
                try:
                    results = correlate_well_suite(wells, [curve])
                    tops_df = correlate_markers_across_wells(wells, curve)
                    st.session_state["corr_results"] = results
                    st.session_state["corr_tops"]    = tops_df
                    st.success(f"✓ {len(results)} pairs correlated")
                except Exception as e:
                    st.error(str(e))

        if "corr_results" in st.session_state:
            results = st.session_state["corr_results"]
            tops_df = st.session_state.get("corr_tops")

            rows = [{"Well A": r.well_a, "Well B": r.well_b,
                     "Curve": r.curve,
                     "Pearson r": f"{r.pearson_r:.3f}",
                     "Depth Lag (m)": f"{r.lag_m:.1f}",
                     "Quality": "✓ Good" if abs(r.pearson_r) > 0.6 else "△ Fair" if abs(r.pearson_r) > 0.3 else "✗ Poor",
                     } for r in results]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            if tops_df is not None and not tops_df.empty:
                st.markdown("**Formation Tops (auto-picked)**")
                st.dataframe(tops_df.round(1), use_container_width=True)

            # Overlay plot
            st.markdown("**GR Overlay (common depth)**")
            try:
                from Project_QLE.analysis.log_correlation import resample_to_common_depth
                fig, ax = plt.subplots(figsize=(10, 5))
                fig.patch.set_facecolor("#0d1b2a"); ax.set_facecolor("#111d2b")
                cmap = plt.get_cmap("tab10")
                for i, w in enumerate(wells):
                    gr = w.get_curve("GR")
                    depth = w.get_depth()
                    if gr is not None and depth is not None:
                        ax.plot(depth, gr, color=cmap(i), lw=0.8,
                                label=w.header.well_name, alpha=0.85)
                ax.set_xlabel("Depth (m)", color="#8ab4d4")
                ax.set_ylabel("GR (GAPI)", color="#8ab4d4")
                ax.legend(fontsize=8, labelcolor="#8ab4d4", facecolor="#0d1b2a")
                ax.tick_params(colors="#8ab4d4"); ax.spines[:].set_color("#1e3a5a")
                ax.grid(color="#1e3a5a", lw=0.4, alpha=0.5)
                ax.set_title("GR Log Overlay", color="#4fc3f7")
                st.pyplot(fig, use_container_width=True)
            except Exception:
                pass


# ════════════════════════════════════════════
#  RESERVOIR SUMMARY
# ════════════════════════════════════════════

elif page == "🏭 Reservoir Summary":
    st.markdown("## 🏭 Reservoir Characterisation")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload and process wells first.")
    else:
        if st.button("▶ Build Reservoir Summaries", type="primary", use_container_width=True):
            from Project_QLE.analysis import (
                PetrophysicsEngine, KMeansFacies, labels_to_zones,
                build_reservoir_summary,
            )
            summaries = []
            prog = st.progress(0)
            for i, well in enumerate(wells):
                prog.progress((i+1)/len(wells), well.header.well_name)
                try:
                    if well.df is None or "PHIE" not in (well.df.columns if well.df is not None else []):
                        df_p = PetrophysicsEngine(well, basin=well.header.basin).run()
                        well.df = df_p
                    df_f = well.df
                    labels = KMeansFacies(n_clusters=5).fit_predict(df_f)
                    df_f["FACIES"] = labels
                    depth = well.get_depth()
                    zones = labels_to_zones(depth, labels) if depth is not None else []
                    rs = build_reservoir_summary(well, df_f, zones)
                    rs.basin = well.header.basin
                    summaries.append(rs)
                except Exception as e:
                    st.warning(f"{well.header.well_name}: {e}")
            st.session_state["reservoirs"] = summaries
            st.success(f"✓ {len(summaries)} reservoir summaries built")

        if "reservoirs" in st.session_state:
            from Project_QLE.analysis.reservoir import (
                stoiip_bbl, giip_mscf, flow_zone_indicator, lorenz_coefficient
            )
            summaries = st.session_state["reservoirs"]

            # Summary table
            rows = [{
                "Well"       : rs.well_name,
                "Basin"      : rs.basin,
                "Net Pay (m)": f"{rs.net_pay_m:.1f}" if rs.net_pay_m else "N/A",
                "φ avg"      : f"{rs.avg_porosity:.3f}" if rs.avg_porosity else "N/A",
                "Sw avg"     : f"{rs.avg_sw:.3f}" if rs.avg_sw else "N/A",
                "k avg (mD)" : f"{rs.avg_perm_mD:.1f}" if rs.avg_perm_mD else "N/A",
                "OWC (m)"    : f"{rs.fluid_contact:.1f}" if rs.fluid_contact else "—",
            } for rs in summaries]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            # Volumetrics
            st.markdown('<div class="section-header">Volumetric Estimation</div>',
                        unsafe_allow_html=True)
            v1, v2, v3 = st.columns(3)
            area  = v1.number_input("Drainage Area (acres)", 100, 50000, 5000, step=100)
            bo    = v2.number_input("Bo (res bbl/STB)", 1.0, 2.0, 1.2, step=0.05)
            bg    = v3.number_input("Bg (res ft³/SCF)", 0.001, 0.02, 0.005, step=0.001, format="%.3f")

            for rs in summaries:
                if rs.net_pay_m and rs.avg_porosity and rs.avg_sw:
                    net_ft = rs.net_pay_m * 3.28084
                    stoiip = stoiip_bbl(area, net_ft, rs.avg_porosity, rs.avg_sw, bo)
                    giip   = giip_mscf(area, net_ft, rs.avg_porosity, rs.avg_sw, bg)
                    c1, c2 = st.columns(2)
                    c1.metric(f"STOIIP – {rs.well_name}", f"{stoiip/1e6:.2f} MMSTB")
                    c2.metric(f"GIIP – {rs.well_name}",   f"{giip/1e6:.2f} Bscf")

            # Zone details
            chosen = st.selectbox("Zone Detail", [rs.well_name for rs in summaries])
            rs_sel = next(r for r in summaries if r.well_name == chosen)
            if rs_sel.zones:
                zone_df = pd.DataFrame([{
                    "Top (m)": z.top, "Base (m)": z.base,
                    "Thickness (m)": round(z.base - z.top, 1),
                    "Facies": z.facies.value, "Fluid": z.fluid.value,
                    "φ": f"{z.porosity:.3f}" if z.porosity else "N/A",
                    "Sw": f"{z.sw:.3f}" if z.sw else "N/A",
                    "k (mD)": f"{z.perm_mD:.1f}" if z.perm_mD else "N/A",
                    "PP (psi)": f"{z.pressure_psi:.0f}" if z.pressure_psi else "N/A",
                } for z in rs_sel.zones])
                st.dataframe(zone_df, use_container_width=True)


# ════════════════════════════════════════════
#  MAP VIEW
# ════════════════════════════════════════════

elif page == "🗺️ Map View":
    st.markdown("## 🗺️ Subsurface Map View")

    tab1, tab2 = st.tabs(["📍 Field Map", "🗺️ Property Map"])

    with tab1:
        from Project_QLE.core.libya_geology import LIBYAN_FIELDS
        st.markdown("**Known Libyan Fields**")
        sel_basin_filter = st.multiselect("Filter by Basin",
                                           ["SIRTE","GHADAMES","MURZUQ","OFFSHORE"],
                                           default=["SIRTE","GHADAMES","MURZUQ","OFFSHORE"])
        fdf = pd.DataFrame([f for f in LIBYAN_FIELDS if f["basin"] in sel_basin_filter])
        if not fdf.empty:
            fdf_map = fdf.rename(columns={"lat":"latitude","lon":"longitude"})
            st.map(fdf_map[["latitude","longitude"]], zoom=4, use_container_width=True)
            st.dataframe(fdf[["name","basin","fluid","api"]].rename(
                columns={"api":"API°","fluid":"Fluid","name":"Field","basin":"Basin"}),
                use_container_width=True)

    with tab2:
        wells = ss("wells", [])
        reservoirs = ss("reservoirs", [])
        wells_with_coords = [w for w in wells
                              if w.header.latitude and w.header.longitude]
        if len(wells_with_coords) < 2:
            st.info("Need ≥2 wells with latitude/longitude in LAS headers for property maps.\n\n"
                    "*(LAS WELL section: LATI / LONG)*")
        else:
            prop = st.selectbox("Property to Map",
                                 ["avg_porosity","avg_sw","avg_perm_mD","net_pay_m"])
            if reservoirs:
                from Project_QLE.ai.map_generator import property_map
                fig = property_map(wells_with_coords, reservoirs, prop=prop,
                                   title=f"{prop.replace('_',' ').title()} – {basin} Basin")
                st.pyplot(fig, use_container_width=True)


# ════════════════════════════════════════════
#  AI INTERPRETATION
# ════════════════════════════════════════════

elif page == "🤖 AI Interpretation":
    st.markdown("## 🤖 AI Interpretation  (Gemini)")

    if not gemini_key:
        st.warning("**No Gemini API key set.** Enter it in the sidebar.\n\n"
                   "Get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey)")
    else:
        reservoirs = ss("reservoirs", [])
        wells      = ss("wells", [])

        tab1, tab2, tab3 = st.tabs(
            ["🏭 Reservoir Narrative", "🔗 Correlation Commentary", "💬 Geological Q&A"]
        )

        with tab1:
            if not reservoirs:
                st.info("Build reservoir summaries first (Reservoir Summary page).")
            else:
                chosen = st.selectbox("Select Well", [r.well_name for r in reservoirs])
                rs = next(r for r in reservoirs if r.well_name == chosen)

                if st.button("▶ Generate Reservoir Report", type="primary"):
                    from Project_QLE.ai import GeminiInterpreter
                    from Project_QLE.analysis import batch_stats
                    well = next((w for w in wells if w.header.well_name == chosen), None)
                    with st.spinner("Gemini is interpreting …"):
                        try:
                            ai = GeminiInterpreter(api_key=gemini_key)
                            stats_for = batch_stats(well, ["GR","PHIE","SW","PERM_mD"]) if well else []
                            narrative = ai.interpret_reservoir(rs, stats_for)
                            st.session_state[f"ai_{chosen}"] = narrative
                        except Exception as e:
                            st.error(str(e))

                key = f"ai_{chosen}"
                if rs.ai_narrative:
                    st.markdown(f'<div class="gemini-box">{rs.ai_narrative.replace(chr(10),"<br>")}</div>',
                                unsafe_allow_html=True)
                elif key in st.session_state:
                    st.markdown(f'<div class="gemini-box">{st.session_state[key].replace(chr(10),"<br>")}</div>',
                                unsafe_allow_html=True)

        with tab2:
            corr_results = ss("corr_results", [])
            if not corr_results:
                st.info("Run Cross-Well Correlation first.")
            else:
                if st.button("▶ Generate Correlation Commentary", type="primary"):
                    from Project_QLE.ai import GeminiInterpreter
                    with st.spinner("Gemini analysing correlations …"):
                        try:
                            ai   = GeminiInterpreter(api_key=gemini_key)
                            tops = ss("corr_tops")
                            text = ai.interpret_correlations(corr_results, tops)
                            st.session_state["ai_corr"] = text
                        except Exception as e:
                            st.error(str(e))
                if "ai_corr" in st.session_state:
                    st.markdown(f'<div class="gemini-box">{st.session_state["ai_corr"].replace(chr(10),"<br>")}</div>',
                                unsafe_allow_html=True)

        with tab3:
            from Project_QLE.core.libya_geology import LIBYAN_BASINS
            st.markdown("Ask a geological question in natural language:")
            q = st.text_area("Question", height=100,
                              placeholder="e.g. What is the typical OWC depth for Intisar reefs in Sirte Basin?")
            context_opt = st.checkbox("Include loaded reservoir data as context", value=True)

            if st.button("▶ Ask Gemini", type="primary") and q:
                from Project_QLE.ai import GeminiInterpreter
                context = ""
                if context_opt and reservoirs:
                    context = "Reservoir data:\n" + "\n".join(
                        f"  {r.well_name}: net_pay={r.net_pay_m:.1f}m φ={r.avg_porosity:.3f} Sw={r.avg_sw:.3f}"
                        for r in reservoirs if r.net_pay_m
                    )
                with st.spinner("Thinking …"):
                    try:
                        ai = GeminiInterpreter(api_key=gemini_key)
                        answer = ai.ask(q, context)
                        st.markdown(f'<div class="gemini-box">{answer.replace(chr(10),"<br>")}</div>',
                                    unsafe_allow_html=True)
                    except Exception as e:
                        st.error(str(e))


# ════════════════════════════════════════════
#  FULL REPORT
# ════════════════════════════════════════════

elif page == "📋 Full Report":
    st.markdown("## 📋 Full Interpretation Report")

    wells      = ss("wells", [])
    reservoirs = ss("reservoirs", [])

    if st.button("▶ Generate Full Report", type="primary", use_container_width=True):
        from Project_QLE.pipeline import QLEPipeline
        project_name = st.text_input("Project Name", "Project_QLE – Libya Exploration") or "Project_QLE"

        with st.spinner("Running full pipeline …"):
            try:
                pipe = QLEPipeline(
                    project_name   = project_name,
                    basin          = basin,
                    use_ai         = bool(gemini_key),
                    gemini_api_key = gemini_key or None,
                )
                pipe._wells = wells
                report = pipe.run()
                st.session_state["report"] = report
                st.success("✓ Report complete")
            except Exception as e:
                st.error(str(e))

    report = ss("report")
    if report:
        st.divider()
        st.markdown(f"### {report.project_name}")
        st.caption(f"Generated: {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}  |  Basin: {report.basin}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Wells", len(report.wells))
        c2.metric("Reservoirs", len(report.reservoirs))
        c3.metric("Warnings", len(report.warnings))

        if report.ai_summary:
            st.markdown('<div class="section-header">AI Executive Summary</div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="gemini-box">{report.ai_summary.replace(chr(10),"<br>")}</div>',
                        unsafe_allow_html=True)

        for rs in report.reservoirs:
            with st.expander(f"📍 {rs.well_name}  |  {rs.basin}"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Net Pay", f"{rs.net_pay_m:.1f} m" if rs.net_pay_m else "N/A")
                col2.metric("Avg φ", f"{rs.avg_porosity:.1%}" if rs.avg_porosity else "N/A")
                col3.metric("Avg Sw", f"{rs.avg_sw:.1%}" if rs.avg_sw else "N/A")
                col4.metric("Avg k", f"{rs.avg_perm_mD:.1f} mD" if rs.avg_perm_mD else "N/A")
                if rs.ai_narrative:
                    st.markdown(f'<div class="gemini-box">{rs.ai_narrative.replace(chr(10),"<br>")}</div>',
                                unsafe_allow_html=True)

        # Export
        st.divider()
        if report.reservoirs:
            export_rows = [{
                "Well": rs.well_name, "Basin": rs.basin,
                "Net Pay (m)": rs.net_pay_m,
                "Avg Porosity": rs.avg_porosity,
                "Avg Sw": rs.avg_sw,
                "Avg Perm (mD)": rs.avg_perm_mD,
                "OWC (m)": rs.fluid_contact,
                "AI Summary": rs.ai_narrative[:200] if rs.ai_narrative else "",
            } for rs in report.reservoirs]
            csv_bytes = pd.DataFrame(export_rows).to_csv(index=False).encode()
            st.download_button("⬇ Export Report CSV", csv_bytes,
                               f"ProjectQLE_report_{report.created_at.strftime('%Y%m%d')}.csv",
                               "text/csv", use_container_width=True)