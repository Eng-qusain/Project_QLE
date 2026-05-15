"""
project_QLE/app.py  –  Project_QLE Streamlit Dashboard
────────────────────────────────────────────────────────
Libya Petroleum Exploration Interpretation Platform

Run:
    streamlit run app.py
"""
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))

# Load .env file if present (GEMINI_API_KEY etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import streamlit as st

# ── Page config – MUST be the very first Streamlit call ──────
st.set_page_config(
    page_title            = "Project_QLE",
    page_icon             = "🛢️",
    layout                = "wide",
    initial_sidebar_state = "expanded",
)

# ── Styling ──────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"] { background:#0d1b2a; }
  [data-testid="stSidebar"] * { color:#e0e8f0 !important; }
  .block-container { padding-top:1.2rem; }
  .metric-card {
    background:linear-gradient(135deg,#0d1b2a,#1a3550);
    border:1px solid #2a5080; border-radius:10px;
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
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
#  SESSION STATE HELPER
# ════════════════════════════════════════════════════════════

def ss(key, default=None):
    """Get or initialise a session state value."""
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


# ════════════════════════════════════════════════════════════
#  DEPENDENCY CHECK (called on upload page)
# ════════════════════════════════════════════════════════════

@st.cache_resource
def _check_deps():
    missing = []
    for pkg, pip_name in [("lasio", "lasio"), ("sklearn", "scikit-learn"), ("scipy", "scipy")]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pip_name)
    return missing


# ════════════════════════════════════════════════════════════
#  GEMINI CLIENT  (cached – one instance per session)
# ════════════════════════════════════════════════════════════

@st.cache_resource
def _get_gemini(api_key: str):
    """Create and cache a GeminiInterpreter so it's not rebuilt on every button click."""
    from project_QLE.ai.gemini_interpreter import GeminiInterpreter
    return GeminiInterpreter(api_key=api_key)


# ════════════════════════════════════════════════════════════
#  LAS PARSING
# ════════════════════════════════════════════════════════════

def parse_uploaded_las(uploaded_file, basin: str):
    """Parse a Streamlit UploadedFile (.las) and return (WellLog, error_str)."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".las", delete=False) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name
        from project_QLE.parsers import parse_las
        well = parse_las(tmp_path)
        well.header.basin = basin
        return well, None
    except Exception as exc:
        return None, str(exc)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)   # always clean up, even on error


# ════════════════════════════════════════════════════════════
#  COLOUR MAPS
# ════════════════════════════════════════════════════════════

TRACK_COLORS = {
    "GR": "#4caf50", "RHOB": "#e91e63", "NPHI": "#2196f3",
    "RT": "#ff9800", "DT": "#9c27b0",   "VSHALE": "#795548",
    "PHIE": "#00bcd4", "SW": "#3f51b5", "SHC": "#26c6da",
    "PERM_mD": "#f44336", "PORE_PRESS_PSI": "#ff5722",
}
LOG_SCALES = {"RT": "log", "PERM_mD": "log"}

FACIES_COLORS = {
    "Sandstone": "#f9a825", "Shale": "#546e7a",
    "Limestone": "#80cbc4", "Dolomite": "#a5d6a7",
    "Anhydrite": "#ce93d8", "Unknown": "#37474f",
}

FLUID_COLORS = {
    "Oil": "#ffb300", "Gas": "#ef5350",
    "Water": "#42a5f5", "Unknown": "#78909c",
}

DARK_BG  = "#0d1b2a"
DARK_AX  = "#111d2b"
DARK_GRID= "#1e3a5a"
TICK_CLR = "#8ab4d4"


# ════════════════════════════════════════════════════════════
#  PLOT HELPER UTILITIES
# ════════════════════════════════════════════════════════════

def _style_ax(ax):
    """Apply dark theme to a matplotlib axes."""
    ax.set_facecolor(DARK_AX)
    ax.tick_params(colors=TICK_CLR, labelsize=6)
    ax.spines[:].set_color(DARK_GRID)
    ax.grid(axis="y", color=DARK_GRID, lw=0.4, alpha=0.6)


def _depth_col(df: pd.DataFrame) -> str:
    for c in ("DEPTH", "DEPT", "MD", "TVD"):
        if c in df.columns:
            return c
    return df.columns[0]


def _filter_depth(df: pd.DataFrame, depth_col: str,
                  d_min: float, d_max: float) -> pd.DataFrame:
    return df[(df[depth_col] >= d_min) & (df[depth_col] <= d_max)]


# ════════════════════════════════════════════════════════════
#  CORE PLOT FUNCTIONS
# ════════════════════════════════════════════════════════════

def make_log_plot(
    df: pd.DataFrame,
    curves: list,
    depth_col: str = "DEPTH",
    title: str = "",
    zones: list = None,          # list of ZoneInterval objects to overlay
    owc_depth: float = None,     # draw OWC/GOC line
    figsize_w: float = 2.8,
) -> plt.Figure:
    """
    Multi-track well log plot.

    zones  : if provided, coloured depth bands are drawn on every track.
    owc_depth : if provided, a dashed horizontal line marks the fluid contact.
    """
    if depth_col not in df.columns:
        depth_col = _depth_col(df)

    depth     = df[depth_col].values
    available = [c for c in curves if c in df.columns and c != depth_col]
    if not available:
        fig, ax = plt.subplots(figsize=(4, 6))
        fig.patch.set_facecolor(DARK_BG)
        ax.set_facecolor(DARK_AX)
        ax.text(0.5, 0.5, "No curves selected", ha="center", va="center", color=TICK_CLR)
        return fig

    n   = len(available)
    fig, axes = plt.subplots(1, n, figsize=(figsize_w * n, 11), sharey=True)
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor(DARK_BG)

    for ax, curve in zip(axes, available):
        _style_ax(ax)
        vals  = df[curve].values.astype(float)
        valid = ~np.isnan(vals)
        color = TRACK_COLORS.get(curve, "#78909c")
        scale = LOG_SCALES.get(curve, "linear")

        # ── Draw the log curve ────────────────────────────
        if scale == "log":
            pos = np.where(vals > 0, vals, np.nan)
            ax.semilogx(pos, depth, color=color, lw=0.8)
            if valid.any() and np.any(pos > 0):
                ax.fill_betweenx(depth,
                                  np.nanmin(pos[~np.isnan(pos)]),
                                  pos, alpha=0.20, color=color)
        else:
            ax.plot(vals, depth, color=color, lw=0.8)
            if valid.any():
                p2, p98 = np.nanpercentile(vals[valid], [2, 98])
                ax.fill_betweenx(depth, p2, vals,
                                  where=(vals >= p2), alpha=0.20, color=color)
                ax.set_xlim(p2 - (p98 - p2) * 0.05,
                             p98 + (p98 - p2) * 0.15)

        # ── Overlay interpreted zone bands ────────────────
        if zones:
            for z in zones:
                fc = FACIES_COLORS.get(z.facies.value, "#37474f")
                ax.axhspan(z.top, z.base, alpha=0.12, color=fc, zorder=0)

        # ── OWC / GOC line ────────────────────────────────
        if owc_depth is not None:
            ax.axhline(owc_depth, color="#42a5f5", lw=1.2,
                       ls="--", alpha=0.9, zorder=5)

        ax.set_xlabel(curve, color=color, fontsize=8, fontweight="bold")
        ax.invert_yaxis()

    axes[0].set_ylabel("Depth (m)", color=TICK_CLR, fontsize=8)
    axes[0].tick_params(axis="y", colors=TICK_CLR)

    if title:
        fig.suptitle(title, color="#4fc3f7", fontsize=9, fontweight="bold", y=1.01)
    plt.tight_layout(w_pad=0.1)
    return fig


def make_comparison_plot(
    well_a,
    well_b,
    curves: list,
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    d_min: float = None,
    d_max: float = None,
    zones_a: list = None,
    zones_b: list = None,
) -> plt.Figure:
    """
    Side-by-side comparison of two wells, sharing the same depth axis.
    Each selected curve gets one column; left half = Well A, right half = Well B.
    A depth marker line shows shared reference.
    """
    dc_a = _depth_col(df_a)
    dc_b = _depth_col(df_b)

    # Clip to requested depth window
    if d_min is not None and d_max is not None:
        df_a = _filter_depth(df_a, dc_a, d_min, d_max)
        df_b = _filter_depth(df_b, dc_b, d_min, d_max)

    available = [c for c in curves if c in df_a.columns or c in df_b.columns]
    if not available:
        fig, ax = plt.subplots(); return fig

    n_cols = len(available)
    fig, axes = plt.subplots(2, n_cols,
                              figsize=(2.6 * n_cols, 12),
                              sharey="row")
    if n_cols == 1:
        axes = axes.reshape(2, 1)
    fig.patch.set_facecolor(DARK_BG)

    row_labels = [well_a.header.well_name, well_b.header.well_name]
    dfs        = [df_a, df_b]
    dcs        = [dc_a, dc_b]
    zone_lists = [zones_a or [], zones_b or []]

    for row_idx, (df, dc, wname, zones) in enumerate(
            zip(dfs, dcs, row_labels, zone_lists)):
        depth = df[dc].values
        for col_idx, curve in enumerate(available):
            ax = axes[row_idx, col_idx]
            _style_ax(ax)
            color = TRACK_COLORS.get(curve, "#78909c")

            if curve in df.columns:
                vals  = df[curve].values.astype(float)
                valid = ~np.isnan(vals)
                if LOG_SCALES.get(curve) == "log":
                    pos = np.where(vals > 0, vals, np.nan)
                    ax.semilogx(pos, depth, color=color, lw=0.8)
                else:
                    ax.plot(vals, depth, color=color, lw=0.8)
                    if valid.any():
                        p2, p98 = np.nanpercentile(vals[valid], [2, 98])
                        ax.fill_betweenx(depth, p2, vals,
                                          where=(vals >= p2), alpha=0.18, color=color)
                        ax.set_xlim(p2 - (p98-p2)*0.05, p98 + (p98-p2)*0.15)
            else:
                ax.text(0.5, 0.5, "N/A", ha="center", va="center",
                        color=TICK_CLR, transform=ax.transAxes, fontsize=8)

            # Zone overlay
            for z in zones:
                fc = FACIES_COLORS.get(z.facies.value, "#37474f")
                ax.axhspan(z.top, z.base, alpha=0.13, color=fc, zorder=0)

            if row_idx == 0:
                ax.set_title(curve, color=color, fontsize=8, fontweight="bold")
            if col_idx == 0:
                ax.set_ylabel(f"{wname}\nDepth (m)", color=TICK_CLR, fontsize=7)
            ax.invert_yaxis()

    plt.tight_layout(h_pad=0.6, w_pad=0.1)
    return fig


def make_facies_track(depth: np.ndarray, facies: np.ndarray) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(1.2, 11))
    fig.patch.set_facecolor(DARK_BG)
    ax.set_facecolor(DARK_AX)
    for i in range(len(depth) - 1):
        ax.fill_betweenx([depth[i], depth[i+1]], 0, 1,
                          color=FACIES_COLORS.get(facies[i], "#37474f"), alpha=0.9)
    ax.set_xlim(0, 1); ax.set_xticks([])
    ax.set_xlabel("Facies", color=TICK_CLR, fontsize=8)
    ax.tick_params(colors=TICK_CLR, labelsize=6)
    ax.spines[:].set_color(DARK_GRID)
    ax.invert_yaxis()
    plt.tight_layout()
    return fig


def make_crossplot(df, x_col, y_col, color_col="VSHALE", title="") -> plt.Figure:
    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
    mask = df[[x_col, y_col]].notna().all(axis=1)
    x = df.loc[mask, x_col].values
    y = df.loc[mask, y_col].values
    c = df.loc[mask, color_col].values if color_col in df.columns else None
    sc = ax.scatter(x, y, c=c, cmap="RdYlGn_r" if c is not None else None,
                    s=4, alpha=0.6, linewidths=0)
    if c is not None:
        cb = plt.colorbar(sc, ax=ax)
        cb.set_label(color_col, color=TICK_CLR, fontsize=8)
        cb.ax.tick_params(colors=TICK_CLR)
    ax.set_xlabel(x_col, color=TICK_CLR)
    ax.set_ylabel(y_col, color=TICK_CLR)
    ax.set_title(title or f"{x_col} vs {y_col}", color="#4fc3f7", fontsize=9)
    ax.tick_params(colors=TICK_CLR)
    ax.spines[:].set_color(DARK_GRID)
    ax.grid(color=DARK_GRID, lw=0.4, alpha=0.5)
    plt.tight_layout()
    return fig


def make_histogram(values, title, color="#4fc3f7", units="") -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
    clean = values[~np.isnan(values)]
    ax.hist(clean, bins=40, color=color, alpha=0.8, edgecolor=DARK_BG, lw=0.4)
    for pct, ls in [(10, "--"), (50, "-"), (90, "--")]:
        val = np.percentile(clean, pct)
        ax.axvline(val, color="#ff9800", lw=1, ls=ls, label=f"P{pct}={val:.2f}")
    ax.legend(fontsize=7, labelcolor=TICK_CLR, facecolor=DARK_BG, edgecolor=DARK_GRID)
    ax.set_title(title, color="#4fc3f7", fontsize=9)
    ax.set_xlabel(units, color=TICK_CLR); ax.set_ylabel("Count", color=TICK_CLR)
    ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
    plt.tight_layout()
    return fig


def _render_gemini_box(text: str):
    """Render Gemini AI output in the styled box, safe line-break handling."""
    safe = text.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    st.markdown(f'<div class="gemini-box">{safe}</div>', unsafe_allow_html=True)


def _metric_card(label, value, sub=""):
    return (
        f'<div class="metric-card">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="sub">{sub}</div>'
        f'</div>'
    )


# ════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🛢️ Project_QLE")
    st.markdown("*Libya Exploration Platform*")
    st.divider()

    page = st.radio(
        "Navigation",
        ["🏠 Home",
         "📁 Data Upload",
         "📊 Well Log Viewer",
         "🔎 Log Comparison",
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


# ════════════════════════════════════════════════════════════
#  HOME
# ════════════════════════════════════════════════════════════

if page == "🏠 Home":
    st.markdown("# 🛢️ Project_QLE")
    st.markdown("### Libya Petroleum Exploration Interpretation Platform")
    st.divider()

    wells = ss("wells", [])
    report = ss("report")
    n_res  = len(report.reservoirs) if report else 0

    c1, c2, c3, c4 = st.columns(4)
    for col, lbl, val, sub in [
        (c1, "Wells Loaded",    str(len(wells)), "LAS files"),
        (c2, "Reservoir Zones", str(n_res),      "interpreted"),
        (c3, "Active Basin",    basin,            "Libya"),
        (c4, "AI Engine",
             "✓ Gemini" if gemini_key else "○ Not set",
             "Gemini 1.5"),
    ]:
        col.markdown(_metric_card(lbl, val, sub), unsafe_allow_html=True)

    st.divider()
    st.markdown("#### Known Libyan Fields")
    try:
        from project_QLE.core.libya_geology import LIBYAN_FIELDS
        fdf = pd.DataFrame(LIBYAN_FIELDS)
        ca, cb = st.columns([2, 1])
        with ca:
            st.map(fdf.rename(columns={"lat": "latitude", "lon": "longitude"})[
                ["latitude", "longitude"]], zoom=4, use_container_width=True)
        with cb:
            st.dataframe(fdf[["name", "basin", "fluid", "api"]].rename(
                columns={"api": "API°", "fluid": "Fluid"}),
                use_container_width=True, height=300)
    except Exception as e:
        st.info(f"Install project dependencies to view field map: {e}")

    st.divider()
    st.markdown("#### Workflow")
    steps = [
        ("📁", "Upload",      "LAS, CSV, PDF"),
        ("⚗️", "Petrophysics","Vshale, φ, Sw, PP"),
        ("🪨", "Facies",      "Rule-based / ML"),
        ("📈", "Statistics",  "P10/P50/P90"),
        ("🏭", "Reservoir",   "Net Pay, OWC"),
        ("🤖", "AI Report",   "Gemini narrative"),
    ]
    cols = st.columns(6)
    for col, (icon, title, desc) in zip(cols, steps):
        col.markdown(
            f'<div class="metric-card">'
            f'<div class="value" style="font-size:1.5rem">{icon}</div>'
            f'<div class="label">{title}</div>'
            f'<div class="sub">{desc}</div></div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════
#  DATA UPLOAD
# ════════════════════════════════════════════════════════════

elif page == "📁 Data Upload":
    st.markdown("## 📁 Data Upload")
    st.divider()

    # Check dependencies here (the one place it's actually useful)
    missing = _check_deps()
    if missing:
        st.error(
            f"**Missing packages:** `{', '.join(missing)}`\n\n"
            f"Run in terminal:\n```\npip install {' '.join(missing)}\n```"
        )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-header">LAS Well Log Files</div>',
                    unsafe_allow_html=True)
        uploaded_las = st.file_uploader(
            "Upload LAS", type=["las"], accept_multiple_files=True,
            label_visibility="collapsed",
        )
        if uploaded_las and st.button("▶ Parse LAS Files", use_container_width=True):
            wells = []
            errs  = []
            prog  = st.progress(0, "Parsing …")
            for i, f in enumerate(uploaded_las):
                prog.progress((i + 1) / len(uploaded_las), f"Parsing {f.name} …")
                well, err = parse_uploaded_las(f, basin)
                if err:
                    errs.append(f"{f.name}: {err}")
                else:
                    wells.append(well)
            st.session_state["wells"] = wells
            for e in errs:
                st.warning(e)
            if wells:
                st.success(f"✓ Loaded {len(wells)} well(s)")

    with col2:
        st.markdown('<div class="section-header">Other Files (CSV, PDF, XML …)</div>',
                    unsafe_allow_html=True)
        uploaded_other = st.file_uploader(
            "Other files", type=["csv", "pdf", "xml", "jpg", "png", "docx"],
            accept_multiple_files=True, label_visibility="collapsed",
        )
        if uploaded_other:
            for f in uploaded_other:
                if f.name.endswith(".csv"):
                    try:
                        df_csv = pd.read_csv(f)
                        st.success(f"✓ {f.name}  ({len(df_csv)} rows × {len(df_csv.columns)} cols)")
                        st.dataframe(df_csv.head(5), use_container_width=True)
                    except Exception as e:
                        st.warning(f"{f.name}: {e}")

    wells = ss("wells", [])
    if wells:
        st.divider()
        st.markdown("#### Loaded Wells")
        rows = [{
            "Well Name" : w.header.well_name,
            "Basin"     : w.header.basin,
            "Start (m)" : w.header.start_depth,
            "Stop (m)"  : w.header.stop_depth,
            "Step (m)"  : w.header.step,
            "N Curves"  : len(w.curves),
            "Curves"    : ", ".join(list(w.curves.keys())[:8]) + ("…" if len(w.curves) > 8 else ""),
        } for w in wells]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ════════════════════════════════════════════════════════════
#  WELL LOG VIEWER  (with zoom + zone overlay)
# ════════════════════════════════════════════════════════════

elif page == "📊 Well Log Viewer":
    st.markdown("## 📊 Well Log Viewer")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload LAS files in **📁 Data Upload** first.")
    else:
        chosen = st.selectbox("Select Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)

        # Build display dataframe
        if well.df is not None and not well.df.empty:
            df_view = well.df.copy()
        else:
            df_view = pd.DataFrame({c: well.curves[c].array for c in well.curves})
            df_view.insert(0, "DEPTH", well.get_depth())

        dc = _depth_col(df_view)
        d_full_min = float(df_view[dc].min())
        d_full_max = float(df_view[dc].max())

        # Curve lists
        raw_curves     = [c for c in well.curves if c not in ("DEPT", "DEPTH", "MD")]
        derived_curves = [c for c in ["VSHALE", "PHIE", "PHID", "SW", "SHC",
                                       "PERM_mD", "PORE_PRESS_PSI"]
                          if c in df_view.columns]
        all_curves = raw_curves + [c for c in derived_curves if c not in raw_curves]

        # ── Controls ─────────────────────────────────────────
        ctrl, plot = st.columns([1, 4])

        with ctrl:
            st.markdown("**Curves**")
            default_sel = [c for c in ["GR", "RHOB", "NPHI", "RT"] if c in all_curves]
            selected = st.multiselect("Curves to display", all_curves,
                                       default=default_sel, label_visibility="collapsed")

            st.markdown("**Depth Window**")
            # Fine zoom: two number inputs give precise control
            z_top  = st.number_input("Top (m)",  value=d_full_min, step=10.0,
                                      min_value=d_full_min, max_value=d_full_max)
            z_base = st.number_input("Base (m)", value=d_full_max, step=10.0,
                                      min_value=d_full_min, max_value=d_full_max)
            if z_top >= z_base:
                st.warning("Top must be shallower than Base.")
                z_base = z_top + 10.0

            show_zones = st.checkbox("Overlay interpreted zones", value=True)
            show_owc   = st.checkbox("Show fluid contact line",   value=True)

        with plot:
            df_zoomed = _filter_depth(df_view, dc, z_top, z_base)

            # Gather zones and OWC from reservoir summaries if available
            zones_overlay = []
            owc_line      = None
            if show_zones or show_owc:
                reservoirs = ss("reservoirs", [])
                rs_match   = next((r for r in reservoirs if r.well_name == chosen), None)
                if rs_match:
                    if show_zones:
                        zones_overlay = rs_match.zones
                    if show_owc:
                        owc_line = rs_match.fluid_contact

            if selected:
                fig = make_log_plot(
                    df_zoomed, selected, dc,
                    title=f"{chosen}  |  {well.header.basin} Basin  "
                          f"[{z_top:.0f}–{z_base:.0f} m]",
                    zones=zones_overlay,
                    owc_depth=owc_line,
                )
                st.pyplot(fig, use_container_width=True)

                # Legend for zones
                if zones_overlay:
                    unique_facies = list({z.facies.value for z in zones_overlay})
                    legend_html   = " &nbsp; ".join(
                        f'<span style="background:{FACIES_COLORS.get(f,"#37474f")};'
                        f'padding:2px 10px;border-radius:4px;font-size:.8rem">{f}</span>'
                        for f in unique_facies
                    )
                    st.markdown(f"**Facies:** {legend_html}", unsafe_allow_html=True)
                if owc_line:
                    st.markdown(
                        f'<span style="color:#42a5f5">── Fluid contact (OWC/GOC): '
                        f'<b>{owc_line:.1f} m</b></span>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Select at least one curve in the panel on the left.")

            # Facies track (if available)
            if "FACIES" in df_zoomed.columns:
                st.markdown("**Facies Track**")
                fig_f = make_facies_track(df_zoomed[dc].values,
                                           df_zoomed["FACIES"].values)
                st.pyplot(fig_f, use_container_width=True)


# ════════════════════════════════════════════════════════════
#  LOG COMPARISON  (side-by-side two wells)
# ════════════════════════════════════════════════════════════

elif page == "🔎 Log Comparison":
    st.markdown("## 🔎 Side-by-Side Log Comparison")
    wells = ss("wells", [])
    if len(wells) < 2:
        st.info("Load **at least 2 wells** to compare them.")
    else:
        well_names = [w.header.well_name for w in wells]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            name_a = st.selectbox("Well A", well_names, index=0)
        with col_b:
            name_b = st.selectbox("Well B", well_names, index=1)
        with col_c:
            compare_curves = st.multiselect(
                "Curves to compare",
                ["GR", "RHOB", "NPHI", "RT", "VSHALE", "PHIE", "SW", "PERM_mD"],
                default=["GR", "RHOB", "NPHI"],
            )

        if name_a == name_b:
            st.warning("Select two different wells.")
        elif not compare_curves:
            st.info("Select at least one curve above.")
        else:
            well_a = next(w for w in wells if w.header.well_name == name_a)
            well_b = next(w for w in wells if w.header.well_name == name_b)

            def _df_for(w):
                if w.df is not None and not w.df.empty:
                    return w.df.copy()
                raw = pd.DataFrame({c: w.curves[c].array for c in w.curves})
                raw.insert(0, "DEPTH", w.get_depth())
                return raw

            df_a = _df_for(well_a)
            df_b = _df_for(well_b)
            dc_a = _depth_col(df_a)
            dc_b = _depth_col(df_b)

            # Common depth range for shared zoom
            common_top  = max(float(df_a[dc_a].min()), float(df_b[dc_b].min()))
            common_base = min(float(df_a[dc_a].max()), float(df_b[dc_b].max()))

            if common_top >= common_base:
                st.warning("The two wells have no overlapping depth range.")
            else:
                col1, col2 = st.columns(2)
                z_top  = col1.number_input("Shared Top (m)",  value=common_top,
                                            step=10.0, min_value=common_top, max_value=common_base)
                z_base = col2.number_input("Shared Base (m)", value=common_base,
                                            step=10.0, min_value=common_top, max_value=common_base)
                if z_top >= z_base:
                    z_base = z_top + 10.0

                show_zones_cmp = st.checkbox("Show interpreted zones on comparison", value=True)

                reservoirs = ss("reservoirs", [])
                zones_a = next((r.zones for r in reservoirs if r.well_name == name_a), []) \
                          if show_zones_cmp else []
                zones_b = next((r.zones for r in reservoirs if r.well_name == name_b), []) \
                          if show_zones_cmp else []

                fig = make_comparison_plot(
                    well_a, well_b,
                    compare_curves,
                    df_a, df_b,
                    d_min=z_top, d_max=z_base,
                    zones_a=zones_a, zones_b=zones_b,
                )
                st.pyplot(fig, use_container_width=True)

                # Quick Pearson correlation table
                if st.checkbox("Show curve correlations between wells", value=False):
                    from project_QLE.analysis import correlate_wells
                    rows = []
                    for curve in compare_curves:
                        try:
                            res = correlate_wells(well_a, well_b, curve)
                            quality = "✓ Good" if abs(res.pearson_r) > 0.6 \
                                      else "△ Fair" if abs(res.pearson_r) > 0.3 \
                                      else "✗ Poor"
                            rows.append({
                                "Curve"       : curve,
                                "Pearson r"   : f"{res.pearson_r:.3f}",
                                "Depth Lag (m)": f"{res.lag_m:.1f}",
                                "Quality"     : quality,
                            })
                        except Exception:
                            rows.append({"Curve": curve, "Pearson r": "N/A",
                                          "Depth Lag (m)": "N/A", "Quality": "—"})
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)


# ════════════════════════════════════════════════════════════
#  PETROPHYSICS
# ════════════════════════════════════════════════════════════

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

            # Basin selector
            basin_opts = ["SIRTE", "GHADAMES", "MURZUQ", "KUFRA", "OFFSHORE"]
            sel_basin  = st.selectbox(
                "Basin",
                basin_opts,
                index=basin_opts.index(well.header.basin)
                      if well.header.basin in basin_opts else 0,
            )

            from project_QLE.core.libya_geology import get_basin_defaults
            defs = get_basin_defaults(sel_basin)

            with st.expander("Advanced Parameters"):
                gr_clean   = st.number_input("GR Clean (GAPI)",  value=float(defs["gr_clean"]))
                gr_shale   = st.number_input("GR Shale (GAPI)",  value=float(defs["gr_shale"]))
                rho_matrix = st.number_input("ρ matrix (g/cc)",  value=float(defs["rho_matrix"]), step=0.01)
                rw         = st.number_input("Rw (ohm-m)",       value=float(defs["rw"]),
                                              step=0.001, format="%.3f")

            if st.button("▶ Run Petrophysics", use_container_width=True, type="primary"):
                with st.spinner("Computing …"):
                    try:
                        from project_QLE.analysis import PetrophysicsEngine
                        df_p = PetrophysicsEngine(
                            well, basin=sel_basin,
                            gr_clean=gr_clean, gr_shale=gr_shale,
                            rho_matrix=rho_matrix, rw=rw,
                        ).run()
                        well.df = df_p
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
                dc   = _depth_col(df_p)

                # Summary metrics
                m = {
                    "Avg PHIE": (f"{df_p['PHIE'].mean()*100:.1f}%" if "PHIE" in df_p.columns else "N/A", "Porosity"),
                    "Avg Sw":   (f"{df_p['SW'].mean()*100:.1f}%"   if "SW"   in df_p.columns else "N/A", "Water Sat"),
                    "Avg Vsh":  (f"{df_p['VSHALE'].mean()*100:.1f}%" if "VSHALE" in df_p.columns else "N/A", "Vshale"),
                    "Avg k":    (f"{df_p['PERM_mD'].mean():.1f} mD" if "PERM_mD" in df_p.columns else "N/A", "Perm"),
                }
                cols = st.columns(4)
                for col, (lbl, (val, sub)) in zip(cols, m.items()):
                    col.markdown(_metric_card(lbl, val, sub), unsafe_allow_html=True)

                # Depth zoom for petrophysics view
                d_min_p = float(df_p[dc].min())
                d_max_p = float(df_p[dc].max())
                pz1, pz2 = st.columns(2)
                pz_top  = pz1.number_input("View Top (m)",  value=d_min_p, step=10.0,
                                            min_value=d_min_p, max_value=d_max_p, key="pz_top")
                pz_base = pz2.number_input("View Base (m)", value=d_max_p, step=10.0,
                                            min_value=d_min_p, max_value=d_max_p, key="pz_base")
                df_pz = _filter_depth(df_p, dc, pz_top, pz_base)

                tab1, tab2, tab3 = st.tabs(["📉 Derived Logs", "⬡ Crossplots", "📋 Data Table"])

                with tab1:
                    derived = [c for c in ["GR", "VSHALE", "PHIE", "SW", "SHC",
                                            "PERM_mD", "PORE_PRESS_PSI"]
                               if c in df_pz.columns]
                    fig = make_log_plot(df_pz, derived, dc,
                                        title=f"{chosen} – Derived  [{pz_top:.0f}–{pz_base:.0f} m]")
                    st.pyplot(fig, use_container_width=True)

                with tab2:
                    c1, c2 = st.columns(2)
                    if "RHOB" in df_p.columns and "NPHI" in df_p.columns:
                        c1.pyplot(make_crossplot(df_p, "NPHI", "RHOB", "VSHALE",
                                                  "ND Crossplot"), use_container_width=True)
                    if "PHIE" in df_p.columns and "PERM_mD" in df_p.columns:
                        c2.pyplot(make_crossplot(df_p, "PHIE", "PERM_mD", "SW",
                                                  "Porosity–Perm"), use_container_width=True)

                with tab3:
                    show_c = [c for c in df_p.columns if c not in (dc,)][:14]
                    st.dataframe(df_p[show_c].round(4), use_container_width=True)
                    st.download_button(
                        "⬇ Download CSV",
                        df_p.to_csv(index=False).encode(),
                        f"{chosen}_petrophysics.csv", "text/csv",
                    )


# ════════════════════════════════════════════════════════════
#  FACIES ANALYSIS
# ════════════════════════════════════════════════════════════

elif page == "🪨 Facies Analysis":
    st.markdown("## 🪨 Facies Analysis")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload and process wells first.")
    else:
        col_cfg, col_out = st.columns([1, 3])

        with col_cfg:
            chosen  = st.selectbox("Well", [w.header.well_name for w in wells])
            well    = next(w for w in wells if w.header.well_name == chosen)
            method  = st.radio("Method", ["KMeans (Unsupervised)", "Rule-Based (GR/RHOB)"])
            n_clust = st.slider("KMeans Clusters", 3, 8, 5) if "KMeans" in method else 5

            if st.button("▶ Classify Facies", use_container_width=True, type="primary"):
                df_src = well.df if well.df is not None else pd.DataFrame(
                    {c: well.curves[c].array for c in well.curves})
                if df_src.empty:
                    st.error("Run Petrophysics first for best results.")
                else:
                    from project_QLE.analysis import KMeansFacies, RuleBasedFacies, labels_to_zones
                    try:
                        labels = (KMeansFacies(n_clusters=n_clust).fit_predict(df_src)
                                  if "KMeans" in method
                                  else RuleBasedFacies().classify(df_src))
                        df_src["FACIES"] = labels
                        well.df = df_src
                        depth = well.get_depth()
                        zones = labels_to_zones(depth, labels) if depth is not None else []
                        st.session_state[f"facies_{chosen}"] = (labels, zones, df_src)
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
                dc = _depth_col(df_f)

                # Depth zoom
                d_min_f = float(df_f[dc].min()); d_max_f = float(df_f[dc].max())
                fz1, fz2 = st.columns(2)
                fz_top  = fz1.number_input("View Top (m)",  value=d_min_f, step=10.0,
                                             min_value=d_min_f, max_value=d_max_f, key="fz_top")
                fz_base = fz2.number_input("View Base (m)", value=d_max_f, step=10.0,
                                             min_value=d_min_f, max_value=d_max_f, key="fz_base")
                df_fz     = _filter_depth(df_f, dc, fz_top, fz_base)
                depth_fz  = df_fz[dc].values
                labels_fz = df_fz["FACIES"].values

                c1, c2 = st.columns(2)
                with c1:
                    fig, ax = plt.subplots(figsize=(4.5, 4.5))
                    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_BG)
                    ax.pie(counts, labels=unique,
                           colors=[FACIES_COLORS.get(u, "#78909c") for u in unique],
                           autopct="%1.0f%%", startangle=90,
                           textprops={"color": "#e0e8f0", "fontsize": 8})
                    ax.set_title("Facies Distribution", color="#4fc3f7")
                    st.pyplot(fig, use_container_width=True)
                with c2:
                    st.pyplot(make_facies_track(depth_fz, labels_fz), use_container_width=True)

                # Log view with zone overlay
                if "GR" in df_f.columns:
                    fig_log = make_log_plot(
                        df_fz,
                        [c for c in ["GR", "RHOB", "NPHI"] if c in df_fz.columns],
                        dc,
                        title=f"{chosen} – Facies Overview [{fz_top:.0f}–{fz_base:.0f} m]",
                        zones=zones,
                    )
                    st.pyplot(fig_log, use_container_width=True)

                st.markdown("**Zone Table**")
                st.dataframe(pd.DataFrame([{
                    "Top (m)": z.top, "Base (m)": z.base,
                    "Thickness (m)": round(z.base - z.top, 1),
                    "Facies": z.facies.value,
                } for z in zones]), use_container_width=True)


# ════════════════════════════════════════════════════════════
#  STATISTICS
# ════════════════════════════════════════════════════════════

elif page == "📈 Statistics":
    st.markdown("## 📈 Statistical Analysis")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload wells first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)
        df_stat = well.df if (well.df is not None and not well.df.empty) \
                  else pd.DataFrame({c: well.curves[c].array for c in well.curves})
        numeric_cols = [c for c in df_stat.columns
                        if pd.api.types.is_numeric_dtype(df_stat[c])
                        and c not in ("DEPTH", "DEPT", "MD")]

        tab1, tab2, tab3, tab4 = st.tabs(
            ["📊 Descriptive", "📉 Histograms", "🔥 Correlation Matrix", "🎲 Monte Carlo"]
        )

        with tab1:
            from project_QLE.analysis import batch_stats
            stats_list = batch_stats(well, numeric_cols[:12])
            if stats_list:
                st.dataframe(pd.DataFrame([{
                    "Curve": s.curve, "N": s.n,
                    "Mean": f"{s.mean:.3f}", "Std": f"{s.std:.3f}",
                    "Min": f"{s.min_val:.3f}", "Max": f"{s.max_val:.3f}",
                    "P10": f"{s.p10:.3f}", "P50": f"{s.p50:.3f}", "P90": f"{s.p90:.3f}",
                    "Skew": f"{s.skewness:.2f}",
                } for s in stats_list]), use_container_width=True)

        with tab2:
            sel_hist = st.selectbox("Curve", numeric_cols)
            if sel_hist:
                st.pyplot(make_histogram(df_stat[sel_hist].values.astype(float),
                                          sel_hist, units=sel_hist), use_container_width=True)

        with tab3:
            from project_QLE.analysis import pearson_matrix
            cross_cols = st.multiselect(
                "Select curves",
                [c for c in numeric_cols if df_stat[c].notna().sum() > 10],
                default=numeric_cols[:6],
            )
            if len(cross_cols) >= 2:
                corr_mat = pearson_matrix(df_stat, cross_cols)
                fig, ax  = plt.subplots(figsize=(7, 6))
                fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_BG)
                im = ax.imshow(corr_mat.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
                ax.set_xticks(range(len(cross_cols)))
                ax.set_xticklabels(cross_cols, rotation=45, color=TICK_CLR, fontsize=8)
                ax.set_yticks(range(len(cross_cols)))
                ax.set_yticklabels(cross_cols, color=TICK_CLR, fontsize=8)
                for i in range(len(cross_cols)):
                    for j in range(len(cross_cols)):
                        ax.text(j, i, f"{corr_mat.values[i,j]:.2f}",
                                ha="center", va="center", fontsize=7, color="white")
                plt.colorbar(im, ax=ax)
                ax.set_title("Pearson Correlation Matrix", color="#4fc3f7")
                st.pyplot(fig, use_container_width=True)

        with tab4:
            from project_QLE.analysis import monte_carlo_porosity
            st.markdown("**Monte Carlo Porosity Uncertainty**")
            c1, c2 = st.columns(2)
            phi_mean = c1.number_input("Mean porosity", 0.0, 0.5, 0.15, step=0.01)
            phi_std  = c2.number_input("Std dev",       0.001, 0.2, 0.04, step=0.005)
            n_mc     = st.slider("Samples", 1000, 50000, 10000, step=1000)
            mc       = monte_carlo_porosity(phi_mean, phi_std, n_mc)
            c1.metric("P10", f"{mc['p10']*100:.1f}%")
            c2.metric("P50", f"{mc['p50']*100:.1f}%")
            c1.metric("P90", f"{mc['p90']*100:.1f}%")
            edges  = np.array(mc["histogram"]["edges"])
            counts = np.array(mc["histogram"]["counts"])
            fig, ax = plt.subplots(figsize=(5, 3))
            fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
            ax.bar(edges[:-1], counts, width=np.diff(edges), color="#4fc3f7", alpha=0.8)
            for p, v in [("P10", mc["p10"]), ("P50", mc["p50"]), ("P90", mc["p90"])]:
                ax.axvline(v, color="#ff9800", lw=1.5, ls="--",
                           label=f"{p}={v*100:.1f}%")
            ax.legend(fontsize=8, labelcolor=TICK_CLR, facecolor=DARK_BG)
            ax.set_xlabel("Porosity", color=TICK_CLR)
            ax.set_ylabel("Count",    color=TICK_CLR)
            ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
            ax.set_title("MC Porosity Distribution", color="#4fc3f7")
            st.pyplot(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════
#  LOG CORRELATION
# ════════════════════════════════════════════════════════════

elif page == "🔗 Log Correlation":
    st.markdown("## 🔗 Cross-Well Log Correlation")
    wells = ss("wells", [])
    if len(wells) < 2:
        st.info("Load **2 or more wells** to run correlation.")
    else:
        curve = st.selectbox("Correlation Curve",
                              ["GR", "RHOB", "NPHI", "RT", "PHIE", "SW"])
        if st.button("▶ Correlate Wells", type="primary"):
            from project_QLE.analysis import correlate_well_suite, correlate_markers_across_wells
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
                     "Quality": "✓ Good" if abs(r.pearson_r) > 0.6
                                else "△ Fair" if abs(r.pearson_r) > 0.3
                                else "✗ Poor"} for r in results]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            if tops_df is not None and not tops_df.empty:
                st.markdown("**Formation Tops (auto-picked)**")
                st.dataframe(tops_df.round(1), use_container_width=True)

            st.markdown("**GR Overlay**")
            fig, ax = plt.subplots(figsize=(10, 5))
            fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
            cmap = plt.get_cmap("tab10")
            for i, w in enumerate(wells):
                gr    = w.get_curve("GR")
                depth = w.get_depth()
                if gr is not None and depth is not None:
                    ax.plot(depth, gr, color=cmap(i), lw=0.8,
                            label=w.header.well_name, alpha=0.85)
            ax.set_xlabel("Depth (m)", color=TICK_CLR)
            ax.set_ylabel("GR (GAPI)", color=TICK_CLR)
            ax.legend(fontsize=8, labelcolor=TICK_CLR, facecolor=DARK_BG)
            ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
            ax.grid(color=DARK_GRID, lw=0.4, alpha=0.5)
            ax.set_title("GR Log Overlay", color="#4fc3f7")
            st.pyplot(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════
#  RESERVOIR SUMMARY
# ════════════════════════════════════════════════════════════

elif page == "🏭 Reservoir Summary":
    st.markdown("## 🏭 Reservoir Characterisation")
    wells = ss("wells", [])
    if not wells:
        st.info("Upload and process wells first.")
    else:
        if st.button("▶ Build Reservoir Summaries", type="primary", use_container_width=True):
            from project_QLE.analysis import (
                PetrophysicsEngine, KMeansFacies,
                labels_to_zones, build_reservoir_summary,
            )
            summaries = []
            prog = st.progress(0)
            for i, well in enumerate(wells):
                prog.progress((i + 1) / len(wells), well.header.well_name)
                try:
                    if well.df is None or "PHIE" not in (well.df.columns if well.df is not None else []):
                        well.df = PetrophysicsEngine(well, basin=well.header.basin).run()
                    df_f   = well.df
                    labels = KMeansFacies(n_clusters=5).fit_predict(df_f)
                    df_f["FACIES"] = labels
                    depth  = well.get_depth()
                    zones  = labels_to_zones(depth, labels) if depth is not None else []
                    rs     = build_reservoir_summary(well, df_f, zones)
                    rs.basin = well.header.basin
                    summaries.append(rs)
                except Exception as e:
                    st.warning(f"{well.header.well_name}: {e}")
            st.session_state["reservoirs"] = summaries
            st.success(f"✓ {len(summaries)} reservoir summaries built")

        if "reservoirs" in st.session_state:
            from project_QLE.analysis.reservoir import stoiip_bbl, giip_mscf
            summaries = st.session_state["reservoirs"]

            rows = [{
                "Well"       : rs.well_name, "Basin": rs.basin,
                "Net Pay (m)": f"{rs.net_pay_m:.1f}" if rs.net_pay_m else "N/A",
                "φ avg"      : f"{rs.avg_porosity:.3f}" if rs.avg_porosity else "N/A",
                "Sw avg"     : f"{rs.avg_sw:.3f}" if rs.avg_sw else "N/A",
                "k avg (mD)" : f"{rs.avg_perm_mD:.1f}" if rs.avg_perm_mD else "N/A",
                "OWC (m)"    : f"{rs.fluid_contact:.1f}" if rs.fluid_contact else "—",
            } for rs in summaries]
            st.dataframe(pd.DataFrame(rows), use_container_width=True)

            # ── Reservoir log view with zone + OWC overlay ─────────
            st.markdown('<div class="section-header">Reservoir Log View</div>',
                        unsafe_allow_html=True)
            chosen_res = st.selectbox("Well", [rs.well_name for rs in summaries],
                                       key="res_log_well")
            rs_sel = next(r for r in summaries if r.well_name == chosen_res)
            well_sel = next((w for w in wells if w.header.well_name == chosen_res), None)
            if well_sel and well_sel.df is not None:
                df_rv = well_sel.df
                dc_rv = _depth_col(df_rv)
                d_min_rv = float(df_rv[dc_rv].min())
                d_max_rv = float(df_rv[dc_rv].max())
                rv1, rv2 = st.columns(2)
                rv_top  = rv1.number_input("Top (m)",  value=d_min_rv, step=10.0,
                                            min_value=d_min_rv, max_value=d_max_rv, key="rv_top")
                rv_base = rv2.number_input("Base (m)", value=d_max_rv, step=10.0,
                                            min_value=d_min_rv, max_value=d_max_rv, key="rv_base")
                df_rv_z = _filter_depth(df_rv, dc_rv, rv_top, rv_base)
                res_curves = [c for c in ["GR", "PHIE", "SW", "PERM_mD"] if c in df_rv_z.columns]
                if res_curves:
                    fig_rv = make_log_plot(
                        df_rv_z, res_curves, dc_rv,
                        title=f"{chosen_res} – Reservoir View [{rv_top:.0f}–{rv_base:.0f} m]",
                        zones=rs_sel.zones,
                        owc_depth=rs_sel.fluid_contact,
                    )
                    st.pyplot(fig_rv, use_container_width=True)
                if rs_sel.fluid_contact:
                    st.info(f"🔵 Fluid contact (OWC/GOC): **{rs_sel.fluid_contact:.1f} m**")

            # ── Volumetrics ────────────────────────────────────────
            st.markdown('<div class="section-header">Volumetric Estimation</div>',
                        unsafe_allow_html=True)
            v1, v2, v3 = st.columns(3)
            area = v1.number_input("Drainage Area (acres)", 100, 50000, 5000, step=100)
            bo   = v2.number_input("Bo (res bbl/STB)", 1.0, 2.0, 1.2, step=0.05)
            bg   = v3.number_input("Bg (res ft³/SCF)", 0.001, 0.02, 0.005,
                                    step=0.001, format="%.3f")
            for rs in summaries:
                if rs.net_pay_m and rs.avg_porosity and rs.avg_sw:
                    net_ft = rs.net_pay_m * 3.28084
                    c1, c2 = st.columns(2)
                    c1.metric(f"STOIIP – {rs.well_name}",
                               f"{stoiip_bbl(area, net_ft, rs.avg_porosity, rs.avg_sw, bo)/1e6:.2f} MMSTB")
                    c2.metric(f"GIIP – {rs.well_name}",
                               f"{giip_mscf(area, net_ft, rs.avg_porosity, rs.avg_sw, bg)/1e6:.2f} Bscf")

            # ── Zone detail table ──────────────────────────────────
            if rs_sel.zones:
                st.markdown("**Zone Detail**")
                st.dataframe(pd.DataFrame([{
                    "Top (m)": z.top, "Base (m)": z.base,
                    "Thickness (m)": round(z.base - z.top, 1),
                    "Facies": z.facies.value, "Fluid": z.fluid.value,
                    "φ": f"{z.porosity:.3f}" if z.porosity else "N/A",
                    "Sw": f"{z.sw:.3f}" if z.sw else "N/A",
                    "k (mD)": f"{z.perm_mD:.1f}" if z.perm_mD else "N/A",
                    "PP (psi)": f"{z.pressure_psi:.0f}" if z.pressure_psi else "N/A",
                } for z in rs_sel.zones]), use_container_width=True)


# ════════════════════════════════════════════════════════════
#  MAP VIEW
# ════════════════════════════════════════════════════════════

elif page == "🗺️ Map View":
    st.markdown("## 🗺️ Subsurface Map View")
    tab1, tab2 = st.tabs(["📍 Field Map", "🗺️ Property Map"])

    with tab1:
        from project_QLE.core.libya_geology import LIBYAN_FIELDS
        sel_basin_f = st.multiselect("Filter by Basin",
                                      ["SIRTE", "GHADAMES", "MURZUQ", "OFFSHORE"],
                                      default=["SIRTE", "GHADAMES", "MURZUQ", "OFFSHORE"])
        fdf = pd.DataFrame([f for f in LIBYAN_FIELDS if f["basin"] in sel_basin_f])
        if not fdf.empty:
            st.map(fdf.rename(columns={"lat": "latitude", "lon": "longitude"})[
                ["latitude", "longitude"]], zoom=4, use_container_width=True)
            st.dataframe(fdf[["name", "basin", "fluid", "api"]].rename(
                columns={"api": "API°", "fluid": "Fluid", "name": "Field", "basin": "Basin"}),
                use_container_width=True)

    with tab2:
        wells      = ss("wells", [])
        reservoirs = ss("reservoirs", [])
        geo_wells  = [w for w in wells if w.header.latitude and w.header.longitude]
        if len(geo_wells) < 2:
            st.info("Need ≥2 wells with LATI / LONG in LAS headers.")
        elif not reservoirs:
            st.info("Build Reservoir Summaries first.")
        else:
            prop = st.selectbox("Property",
                                 ["avg_porosity", "avg_sw", "avg_perm_mD", "net_pay_m"])
            from project_QLE.ai.map_generator import property_map
            fig = property_map(geo_wells, reservoirs, prop=prop,
                               title=f"{prop.replace('_',' ').title()} – {basin} Basin")
            st.pyplot(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════
#  AI INTERPRETATION
# ════════════════════════════════════════════════════════════

elif page == "🤖 AI Interpretation":
    st.markdown("## 🤖 AI Interpretation  (Gemini)")

    if not gemini_key:
        st.warning(
            "**No Gemini API key set.** Enter it in the sidebar.\n\n"
            "Get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey)"
        )
    else:
        reservoirs = ss("reservoirs", [])
        wells      = ss("wells", [])

        tab1, tab2, tab3 = st.tabs(
            ["🏭 Reservoir Narrative", "🔗 Correlation Commentary", "💬 Geological Q&A"]
        )

        with tab1:
            if not reservoirs:
                st.info("Build reservoir summaries first.")
            else:
                chosen = st.selectbox("Well", [r.well_name for r in reservoirs])
                rs     = next(r for r in reservoirs if r.well_name == chosen)

                if st.button("▶ Generate Reservoir Report", type="primary"):
                    from project_QLE.analysis import batch_stats
                    well_m = next((w for w in wells if w.header.well_name == chosen), None)
                    with st.spinner("Gemini is interpreting …"):
                        try:
                            ai = _get_gemini(gemini_key)
                            stats_for = batch_stats(well_m, ["GR", "PHIE", "SW", "PERM_mD"]) \
                                        if well_m else []
                            narrative = ai.interpret_reservoir(rs, stats_for)
                            st.session_state[f"ai_{chosen}"] = narrative
                        except Exception as e:
                            st.error(str(e))

                narrative = rs.ai_narrative or st.session_state.get(f"ai_{chosen}", "")
                if narrative:
                    _render_gemini_box(narrative)

        with tab2:
            corr_results = ss("corr_results", [])
            if not corr_results:
                st.info("Run Cross-Well Correlation first.")
            else:
                if st.button("▶ Generate Correlation Commentary", type="primary"):
                    with st.spinner("Analysing correlations …"):
                        try:
                            ai   = _get_gemini(gemini_key)
                            tops = ss("corr_tops")
                            text = ai.interpret_correlations(corr_results, tops)
                            st.session_state["ai_corr"] = text
                        except Exception as e:
                            st.error(str(e))
                if "ai_corr" in st.session_state:
                    _render_gemini_box(st.session_state["ai_corr"])

        with tab3:
            st.markdown("Ask a geological question:")
            q = st.text_area(
                "Question", height=100,
                placeholder="e.g. What is the typical OWC depth for Intisar reefs in Sirte Basin?",
            )
            context_opt = st.checkbox("Include reservoir data as context", value=True)

            if st.button("▶ Ask Gemini", type="primary") and q:
                context = ""
                if context_opt and reservoirs:
                    context = "Reservoir data:\n" + "\n".join(
                        f"  {r.well_name}: net_pay={r.net_pay_m:.1f}m "
                        f"φ={r.avg_porosity:.3f} Sw={r.avg_sw:.3f}"
                        for r in reservoirs if r.net_pay_m
                    )
                with st.spinner("Thinking …"):
                    try:
                        ai     = _get_gemini(gemini_key)
                        answer = ai.ask(q, context)
                        _render_gemini_box(answer)
                    except Exception as e:
                        st.error(str(e))


# ════════════════════════════════════════════════════════════
#  FULL REPORT
# ════════════════════════════════════════════════════════════

elif page == "📋 Full Report":
    st.markdown("## 📋 Full Interpretation Report")

    # Project name input ABOVE the button (fixes the Streamlit widget-inside-button bug)
    project_name = st.text_input("Project Name", value="Project_QLE – Libya Exploration")

    wells      = ss("wells", [])
    reservoirs = ss("reservoirs", [])

    if st.button("▶ Generate Full Report", type="primary", use_container_width=True):
        if not wells:
            st.warning("Load wells first.")
        else:
            from project_QLE.pipeline import QLEPipeline
            with st.spinner("Running full pipeline …"):
                try:
                    pipe = QLEPipeline(
                        project_name   = project_name or "Project_QLE",
                        basin          = basin,
                        use_ai         = bool(gemini_key),
                        gemini_api_key = gemini_key or None,
                    )
                    for w in wells:
                        pipe.add_well(w)
                    report = pipe.run()
                    st.session_state["report"] = report
                    st.success("✓ Report complete")
                except Exception as e:
                    st.error(str(e))

    report = ss("report")
    if report:
        st.divider()
        st.markdown(f"### {report.project_name}")
        st.caption(
            f"Generated: {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}  "
            f"|  Basin: {report.basin}"
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Wells",      len(report.wells))
        c2.metric("Reservoirs", len(report.reservoirs))
        c3.metric("Warnings",   len(report.warnings))

        if report.ai_summary:
            st.markdown('<div class="section-header">AI Executive Summary</div>',
                        unsafe_allow_html=True)
            _render_gemini_box(report.ai_summary)

        for rs in report.reservoirs:
            with st.expander(f"📍 {rs.well_name}  |  {rs.basin}"):
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Net Pay", f"{rs.net_pay_m:.1f} m" if rs.net_pay_m else "N/A")
                r2.metric("Avg φ",   f"{rs.avg_porosity:.1%}" if rs.avg_porosity else "N/A")
                r3.metric("Avg Sw",  f"{rs.avg_sw:.1%}" if rs.avg_sw else "N/A")
                r4.metric("Avg k",   f"{rs.avg_perm_mD:.1f} mD" if rs.avg_perm_mD else "N/A")
                if rs.ai_narrative:
                    _render_gemini_box(rs.ai_narrative)

        if report.warnings:
            with st.expander(f"⚠ {len(report.warnings)} warning(s)"):
                for w in report.warnings:
                    st.caption(w)

        st.divider()
        if report.reservoirs:
            export_df = pd.DataFrame([{
                "Well": rs.well_name, "Basin": rs.basin,
                "Net Pay (m)": rs.net_pay_m,
                "Avg Porosity": rs.avg_porosity,
                "Avg Sw": rs.avg_sw, "Avg Perm (mD)": rs.avg_perm_mD,
                "OWC (m)": rs.fluid_contact,
                "AI Summary": rs.ai_narrative[:200] if rs.ai_narrative else "",
            } for rs in report.reservoirs])
            st.download_button(
                "⬇ Export Report CSV",
                export_df.to_csv(index=False).encode(),
                f"ProjectQLE_report_{report.created_at.strftime('%Y%m%d')}.csv",
                "text/csv",
                use_container_width=True,
            )