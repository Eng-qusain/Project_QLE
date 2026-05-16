"""
project_QLE/app.py  –  Project_QLE Streamlit Dashboard
────────────────────────────────────────────────────────
Libya Petroleum Exploration & Interpretation Platform

Run:  streamlit run app.py
"""
import os
import sys
import tempfile
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(__file__))
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

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="Project_QLE",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Bootstrap database ───────────────────────────────────────
try:
    from project_QLE.database import init_all
    init_all()
except Exception as _db_err:
    pass   # non-fatal – platform may not have SQLAlchemy yet

# ── Styling ───────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stSidebar"]{background:#0d1b2a}
  [data-testid="stSidebar"] *{color:#e0e8f0 !important}
  .block-container{padding-top:1.2rem}
  .mc{background:linear-gradient(135deg,#0d1b2a,#1a3550);border:1px solid #2a5080;
      border-radius:10px;padding:16px 18px;text-align:center;margin:4px 0}
  .mc .lbl{font-size:.75rem;color:#8ab4d4;letter-spacing:.06em;text-transform:uppercase}
  .mc .val{font-size:1.6rem;font-weight:700;color:#4fc3f7;margin-top:4px}
  .mc .sub{font-size:.7rem;color:#607d8b;margin-top:2px}
  .sh{border-left:4px solid #4fc3f7;padding-left:12px;font-size:1.05rem;
      font-weight:600;color:#e0e8f0;margin:18px 0 10px}
  .gb{background:#0a1628;border:1px solid #1e4060;border-radius:8px;
      padding:14px 18px;font-size:.87rem;line-height:1.7;color:#cdd8e3}
  .badge-good{background:#1b3a1b;color:#81c784;border:1px solid #388e3c;
              border-radius:4px;padding:2px 10px;font-weight:700}
  .badge-fair{background:#3a2d0a;color:#ffb74d;border:1px solid #f57c00;
              border-radius:4px;padding:2px 10px;font-weight:700}
  .badge-poor{background:#3a1010;color:#ef9a9a;border:1px solid #c62828;
              border-radius:4px;padding:2px 10px;font-weight:700}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
#  CONSTANTS
# ════════════════════════════════════════════════════════════
DARK_BG   = "#0d1b2a"
DARK_AX   = "#111d2b"
DARK_GRID = "#1e3a5a"
TICK_CLR  = "#8ab4d4"

TRACK_COLORS = {
    "GR":"#4caf50","RHOB":"#e91e63","NPHI":"#2196f3","RT":"#ff9800",
    "DT":"#9c27b0","VSHALE":"#795548","PHIE":"#00bcd4","SW":"#3f51b5",
    "SH":"#26c6da","PERM_mD":"#f44336","PORE_PRESS_PSI":"#ff5722",
}
LOG_SCALES = {"RT":"log","PERM_mD":"log"}

FACIES_COLORS = {
    "Sandstone":"#f9a825","Shale":"#546e7a","Limestone":"#80cbc4",
    "Dolomite":"#a5d6a7","Anhydrite":"#ce93d8","Unknown":"#37474f",
}

QUALITY_BADGE = {
    "Excellent": "badge-good",
    "Good":      "badge-good",
    "Fair":      "badge-fair",
    "Poor":      "badge-poor",
}

# ════════════════════════════════════════════════════════════
#  SESSION STATE
# ════════════════════════════════════════════════════════════
def ss(key, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]

# ════════════════════════════════════════════════════════════
#  ACCESS CONTROL
# ════════════════════════════════════════════════════════════
def _check_access() -> bool:
    """Return True if the user has a valid access key in session."""
    return bool(ss("authenticated_user"))

def _login_wall():
    """Show login form and block app until authenticated."""
    st.markdown("## 🔐 Project_QLE — Access Required")
    st.markdown("This platform requires an **access key** issued by the project owner.")
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        key_input = st.text_input("Access Key", type="password",
                                   placeholder="QLE-xxxxxxxxxxxxxxxxxxxx")
        if st.button("🔑 Enter", use_container_width=True, type="primary"):
            try:
                from project_QLE.database.auth import authenticate
                user = authenticate(key_input)
                if user:
                    st.session_state["authenticated_user"] = {
                        "username": user.username,
                        "role":     user.role,
                    }
                    st.success(f"✓ Welcome, {user.username}!")
                    st.rerun()
                else:
                    st.error("Invalid or inactive key. Contact the project owner.")
            except Exception as e:
                # Auth system not yet set up — allow bypass in dev
                st.warning(f"Auth system not available ({e}). Running in dev mode.")
                st.session_state["authenticated_user"] = {"username": "dev", "role": "owner"}
                st.rerun()
    st.stop()

# Check access before rendering anything
if not _check_access():
    _login_wall()

_auth_user = ss("authenticated_user", {})
_is_owner  = _auth_user.get("role") == "owner"

# ════════════════════════════════════════════════════════════
#  CACHES
# ════════════════════════════════════════════════════════════
@st.cache_resource
def _check_deps():
    missing = []
    for pkg, pip_n in [("lasio","lasio"),("sklearn","scikit-learn"),("scipy","scipy")]:
        try: __import__(pkg)
        except ImportError: missing.append(pip_n)
    return missing

@st.cache_resource
def _get_gemini(api_key: str):
    from project_QLE.ai.gemini_interpreter import GeminiInterpreter
    return GeminiInterpreter(api_key=api_key)

# ════════════════════════════════════════════════════════════
#  LAS PARSING HELPER
# ════════════════════════════════════════════════════════════
def parse_uploaded_las(uploaded_file, basin: str):
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
            os.unlink(tmp_path)

# ════════════════════════════════════════════════════════════
#  PLOT HELPERS
# ════════════════════════════════════════════════════════════
def _style_ax(ax):
    ax.set_facecolor(DARK_AX)
    ax.tick_params(colors=TICK_CLR, labelsize=6)
    ax.spines[:].set_color(DARK_GRID)
    ax.grid(axis="y", color=DARK_GRID, lw=0.4, alpha=0.6)

def _depth_col(df):
    for c in ("DEPTH","DEPT","MD","TVD"): 
        if c in df.columns: return c
    return df.columns[0]

def _filter_depth(df, dc, d_min, d_max):
    return df[(df[dc] >= d_min) & (df[dc] <= d_max)]

def _mc(lbl, val, sub=""):
    return (f'<div class="mc"><div class="lbl">{lbl}</div>'
            f'<div class="val">{val}</div><div class="sub">{sub}</div></div>')

def _gb(text):
    safe = (str(text).replace("<","&lt;").replace(">","&gt;")
            .replace("\n","<br>"))
    st.markdown(f'<div class="gb">{safe}</div>', unsafe_allow_html=True)

# ── Main log plot ─────────────────────────────────────────────
def make_log_plot(df, curves, depth_col="DEPTH", title="",
                  zones=None, owc_depth=None, figsize_w=2.8):
    if depth_col not in df.columns:
        depth_col = _depth_col(df)
    depth     = df[depth_col].values
    available = [c for c in curves if c in df.columns and c != depth_col]
    if not available:
        fig, ax = plt.subplots(figsize=(4,6))
        fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
        ax.text(0.5,0.5,"No curves",ha="center",va="center",color=TICK_CLR)
        return fig

    n   = len(available)
    fig, axes = plt.subplots(1, n, figsize=(figsize_w*n, 11), sharey=True)
    if n == 1: axes = [axes]
    fig.patch.set_facecolor(DARK_BG)

    for ax, curve in zip(axes, available):
        _style_ax(ax)
        vals  = df[curve].values.astype(float)
        valid = ~np.isnan(vals)
        color = TRACK_COLORS.get(curve, "#78909c")

        if LOG_SCALES.get(curve) == "log":
            pos = np.where(vals > 0, vals, np.nan)
            ax.semilogx(pos, depth, color=color, lw=0.8)
            if valid.any() and np.any(pos > 0):
                ax.fill_betweenx(depth, np.nanmin(pos[~np.isnan(pos)]),
                                  pos, alpha=0.18, color=color)
        else:
            ax.plot(vals, depth, color=color, lw=0.8)
            if valid.any():
                p2, p98 = np.nanpercentile(vals[valid], [2,98])
                ax.fill_betweenx(depth, p2, vals,
                                  where=(vals >= p2), alpha=0.18, color=color)
                ax.set_xlim(p2 - (p98-p2)*0.05, p98 + (p98-p2)*0.15)

        if zones:
            for z in zones:
                ax.axhspan(z.top, z.base, alpha=0.12,
                            color=FACIES_COLORS.get(z.facies.value,"#37474f"), zorder=0)
        if owc_depth is not None:
            ax.axhline(owc_depth, color="#42a5f5", lw=1.2, ls="--", zorder=5)

        ax.set_xlabel(curve, color=color, fontsize=8, fontweight="bold")
        ax.invert_yaxis()

    axes[0].set_ylabel("Depth (m)", color=TICK_CLR, fontsize=8)
    axes[0].tick_params(axis="y", colors=TICK_CLR)
    if title:
        fig.suptitle(title, color="#4fc3f7", fontsize=9, fontweight="bold", y=1.01)
    plt.tight_layout(w_pad=0.1)
    return fig

# ── Side-by-side comparison (TRUE side-by-side in one figure) ─
def make_comparison_plot(well_a, well_b, curves, df_a, df_b,
                          d_min=None, d_max=None,
                          zones_a=None, zones_b=None):
    """
    Proper side-by-side layout:
      [Well A: curve1 | curve2 | curve3] | [Well B: curve1 | curve2 | curve3]

    All tracks share the same depth (y) axis.
    Dashed vertical separator divides the two wells.
    """
    dc_a = _depth_col(df_a); dc_b = _depth_col(df_b)
    if d_min is not None:
        df_a = _filter_depth(df_a, dc_a, d_min, d_max)
        df_b = _filter_depth(df_b, dc_b, d_min, d_max)

    available = [c for c in curves if c in df_a.columns or c in df_b.columns]
    if not available:
        return plt.figure()

    n = len(available)
    total_cols = n * 2   # n tracks per well × 2 wells

    fig, all_ax = plt.subplots(1, total_cols,
                                figsize=(2.4 * total_cols, 11),
                                sharey=True)
    if total_cols == 1: all_ax = [all_ax]
    fig.patch.set_facecolor(DARK_BG)

    axes_a = all_ax[:n]          # left half  → Well A
    axes_b = all_ax[n:]          # right half → Well B

    name_a = well_a.header.well_name
    name_b = well_b.header.well_name

    for side_axes, df, dc, wname, zones in [
        (axes_a, df_a, dc_a, name_a, zones_a or []),
        (axes_b, df_b, dc_b, name_b, zones_b or []),
    ]:
        depth = df[dc].values
        for col_i, (ax, curve) in enumerate(zip(side_axes, available)):
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
                        p2, p98 = np.nanpercentile(vals[valid], [2,98])
                        ax.fill_betweenx(depth, p2, vals,
                                          where=(vals >= p2), alpha=0.18, color=color)
                        ax.set_xlim(p2-(p98-p2)*0.05, p98+(p98-p2)*0.15)
            else:
                ax.text(0.5, 0.5, "N/A", ha="center", va="center",
                        color=TICK_CLR, transform=ax.transAxes, fontsize=8)

            for z in zones:
                ax.axhspan(z.top, z.base, alpha=0.12,
                            color=FACIES_COLORS.get(z.facies.value,"#37474f"), zorder=0)

            ax.set_title(curve, color=color, fontsize=7, fontweight="bold", pad=2)
            ax.invert_yaxis()

        # Well name label on the first track of each group
        side_axes[0].set_ylabel(f"{wname}\nDepth (m)", color="#4fc3f7",
                                 fontsize=7, fontweight="bold")
        side_axes[0].tick_params(axis="y", colors=TICK_CLR)

    # Draw a vertical separator line between the two wells
    try:
        sep_ax = axes_a[-1]
        sep_ax.axvline(sep_ax.get_xlim()[1], color="#4fc3f7",
                        lw=1.5, ls=":", alpha=0.6)
    except Exception:
        pass

    plt.tight_layout(w_pad=0.05)
    return fig

# ── Facies track ──────────────────────────────────────────────
def make_facies_track(depth, facies):
    fig, ax = plt.subplots(figsize=(1.2, 11))
    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
    for i in range(len(depth)-1):
        ax.fill_betweenx([depth[i], depth[i+1]], 0, 1,
                          color=FACIES_COLORS.get(facies[i],"#37474f"), alpha=0.9)
    ax.set_xlim(0,1); ax.set_xticks([])
    ax.set_xlabel("Facies", color=TICK_CLR, fontsize=8)
    ax.tick_params(colors=TICK_CLR, labelsize=6)
    ax.spines[:].set_color(DARK_GRID); ax.invert_yaxis()
    plt.tight_layout(); return fig

def make_crossplot(df, x_col, y_col, color_col="VSHALE", title=""):
    fig, ax = plt.subplots(figsize=(6,5))
    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
    mask = df[[x_col, y_col]].notna().all(axis=1)
    x = df.loc[mask, x_col].values; y = df.loc[mask, y_col].values
    c = df.loc[mask, color_col].values if color_col in df.columns else None
    sc = ax.scatter(x, y, c=c, cmap="RdYlGn_r" if c is not None else None,
                    s=4, alpha=0.6, linewidths=0)
    if c is not None:
        cb = plt.colorbar(sc, ax=ax); cb.set_label(color_col, color=TICK_CLR, fontsize=8)
        cb.ax.tick_params(colors=TICK_CLR)
    ax.set_xlabel(x_col, color=TICK_CLR); ax.set_ylabel(y_col, color=TICK_CLR)
    ax.set_title(title or f"{x_col} vs {y_col}", color="#4fc3f7", fontsize=9)
    ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
    ax.grid(color=DARK_GRID, lw=0.4, alpha=0.5)
    plt.tight_layout(); return fig

def make_histogram(values, title, color="#4fc3f7", units=""):
    fig, ax = plt.subplots(figsize=(5,3.5))
    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
    clean = values[~np.isnan(values)]
    ax.hist(clean, bins=40, color=color, alpha=0.8, edgecolor=DARK_BG, lw=0.4)
    for pct, ls in [(10,"--"),(50,"-"),(90,"--")]:
        v = np.percentile(clean, pct)
        ax.axvline(v, color="#ff9800", lw=1, ls=ls, label=f"P{pct}={v:.3f}")
    ax.legend(fontsize=7, labelcolor=TICK_CLR, facecolor=DARK_BG, edgecolor=DARK_GRID)
    ax.set_title(title, color="#4fc3f7", fontsize=9)
    ax.set_xlabel(units, color=TICK_CLR); ax.set_ylabel("Count", color=TICK_CLR)
    ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
    plt.tight_layout(); return fig

# ════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🛢️ Project_QLE")
    st.markdown(f"*{_auth_user.get('username','')}*  {'👑' if _is_owner else ''}")
    st.divider()

    ALL_PAGES = [
        "🏠 Home",
        "📁 Data Upload",
        "📂 Project Manager",
        "📊 Well Log Viewer",
        "🔎 Log Comparison",
        "⚗️ Petrophysics",
        "📊 Petro Summary",
        "🪨 Facies Analysis",
        "📈 Statistics",
        "🔗 Log Correlation",
        "🏭 Reservoir Summary",
        "🗻 Formation Tops",
        "🔬 DST Tests",
        "🤖 ML Comparison",
        "📉 Trend Analysis",
        "🗺️ Map View",
        "🧠 AI Interpretation",
        "📋 Full Report",
    ]

    page = st.radio("Navigation", ALL_PAGES, label_visibility="collapsed")
    st.divider()

    st.markdown("**Basin**")
    basin = st.selectbox("Active Basin",
                          ["SIRTE","GHADAMES","MURZUQ","KUFRA","OFFSHORE"],
                          label_visibility="collapsed")

    st.markdown("**Gemini API Key**")
    gemini_key = st.text_input("Gemini Key",
                                value=os.environ.get("GEMINI_API_KEY",""),
                                type="password", label_visibility="collapsed",
                                placeholder="AIza…")
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

    st.divider()
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state["authenticated_user"] = None
        st.rerun()
    st.caption("Project_QLE v1.0  |  Libya NOC")


# ════════════════════════════════════════════════════════════
#  PAGE: HOME
# ════════════════════════════════════════════════════════════
if page == "🏠 Home":
    st.markdown("# 🛢️ Project_QLE")
    st.markdown("### Libya Petroleum Exploration & Interpretation Platform")
    st.divider()

    wells  = ss("wells", [])
    report = ss("report")
    n_res  = len(report.reservoirs) if report else 0

    c1,c2,c3,c4 = st.columns(4)
    for col, lbl, val, sub in [
        (c1, "Wells Loaded", str(len(wells)), "LAS files"),
        (c2, "Reservoir Zones", str(n_res), "interpreted"),
        (c3, "Active Basin", basin, "Libya"),
        (c4, "AI Engine", "✓ Gemini" if gemini_key else "○ Not set", "Gemini 1.5"),
    ]:
        col.markdown(_mc(lbl, val, sub), unsafe_allow_html=True)

    st.divider()
    st.markdown("#### Libyan Fields")
    try:
        from project_QLE.core.libya_geology import LIBYAN_FIELDS
        fdf = pd.DataFrame(LIBYAN_FIELDS)
        ca, cb = st.columns([2,1])
        with ca:
            st.map(fdf.rename(columns={"lat":"latitude","lon":"longitude"})[
                ["latitude","longitude"]], zoom=4, use_container_width=True)
        with cb:
            st.dataframe(fdf[["name","basin","fluid","api"]].rename(
                columns={"api":"API°","fluid":"Fluid"}),
                use_container_width=True, height=300)
    except Exception as e:
        st.info(f"Install dependencies: {e}")

# ════════════════════════════════════════════════════════════
#  PAGE: DATA UPLOAD
# ════════════════════════════════════════════════════════════
elif page == "📁 Data Upload":
    st.markdown("## 📁 Data Upload")
    st.divider()

    missing = _check_deps()
    if missing:
        st.error(f"Missing packages: `{', '.join(missing)}`\n\n```\npip install {' '.join(missing)}\n```")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="sh">LAS Well Log Files</div>', unsafe_allow_html=True)
        uploaded_las = st.file_uploader("Upload LAS", type=["las"],
                                         accept_multiple_files=True,
                                         label_visibility="collapsed")
        if uploaded_las and st.button("▶ Parse LAS Files", use_container_width=True):
            wells, errs = [], []
            prog = st.progress(0, "Parsing …")
            for i, f in enumerate(uploaded_las):
                prog.progress((i+1)/len(uploaded_las), f"Parsing {f.name} …")
                well, err = parse_uploaded_las(f, basin)
                (errs if err else wells).append(err if err else well)
            st.session_state["wells"] = wells
            for e in errs: st.warning(e)
            if wells: st.success(f"✓ Loaded {len(wells)} well(s)")

    with col2:
        st.markdown('<div class="sh">Other Files (CSV, PDF …)</div>', unsafe_allow_html=True)
        uploaded_other = st.file_uploader("Other files",
                                           type=["csv","pdf","xml","jpg","png","docx"],
                                           accept_multiple_files=True,
                                           label_visibility="collapsed")
        if uploaded_other:
            for f in uploaded_other:
                if f.name.endswith(".csv"):
                    try:
                        df_csv = pd.read_csv(f)
                        st.success(f"✓ {f.name}  ({len(df_csv)} rows)")
                        st.dataframe(df_csv.head(5), use_container_width=True)
                    except Exception as e:
                        st.warning(f"{f.name}: {e}")

    wells = ss("wells",[])
    if wells:
        st.divider()
        st.markdown("#### Loaded Wells")
        st.dataframe(pd.DataFrame([{
            "Well Name": w.header.well_name, "Basin": w.header.basin,
            "Start (m)": w.header.start_depth, "Stop (m)": w.header.stop_depth,
            "N Curves": len(w.curves),
            "Curves": ", ".join(list(w.curves.keys())[:8]) + ("…" if len(w.curves)>8 else ""),
        } for w in wells]), use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: PROJECT MANAGER
# ════════════════════════════════════════════════════════════
elif page == "📂 Project Manager":
    st.markdown("## 📂 Project Manager")
    st.divider()

    tab_list, tab_new = st.tabs(["📋 All Projects", "➕ New Project"])

    with tab_new:
        pname = st.text_input("Project Name")
        pbas  = st.selectbox("Basin", ["SIRTE","GHADAMES","MURZUQ","KUFRA","OFFSHORE"])
        pdesc = st.text_area("Description", height=80)
        if st.button("✅ Create Project", type="primary") and pname:
            try:
                from project_QLE.database import create_project
                create_project(pname, pbas, pdesc)
                st.success(f"✓ Project '{pname}' created")
            except Exception as e:
                st.error(str(e))

    with tab_list:
        try:
            from project_QLE.database import list_projects
            projects = list_projects()
            if not projects:
                st.info("No projects yet. Create one in the 'New Project' tab.")
            else:
                for proj in projects:
                    with st.expander(f"📁 {proj.name}  ({proj.basin})"):
                        st.caption(f"Created: {proj.created_at.strftime('%Y-%m-%d')}  |  {proj.description or '—'}")
                        # Load project wells
                        from project_QLE.database import get_wells_in_project
                        db_wells = get_wells_in_project(proj.id)
                        if db_wells:
                            st.dataframe(pd.DataFrame([{
                                "Well": w.well_name, "Start": w.start_depth,
                                "Stop": w.stop_depth, "LAS": w.las_file_path or "—",
                            } for w in db_wells]), use_container_width=True)
                        else:
                            st.caption("No wells saved to this project yet.")

                        # Save loaded wells to this project
                        wells = ss("wells",[])
                        if wells and st.button(f"💾 Save loaded wells to '{proj.name}'",
                                                key=f"save_{proj.id}"):
                            from project_QLE.database import save_well
                            for w in wells:
                                try:
                                    save_well(proj.id, w.header.well_name,
                                              las_file_path=str(w.source) if w.source else "",
                                              latitude=w.header.latitude,
                                              longitude=w.header.longitude,
                                              start_depth=w.header.start_depth,
                                              stop_depth=w.header.stop_depth,
                                              step=w.header.step)
                                except Exception:
                                    pass
                            st.success("Wells saved to project.")

                        if _is_owner:
                            if st.button(f"🗑 Delete '{proj.name}'", key=f"del_{proj.id}"):
                                from project_QLE.database import delete_project
                                delete_project(proj.name)
                                st.rerun()
        except Exception as e:
            st.warning(f"Database not available: {e}")

# ════════════════════════════════════════════════════════════
#  PAGE: WELL LOG VIEWER (with zoom + zone overlay)
# ════════════════════════════════════════════════════════════
elif page == "📊 Well Log Viewer":
    st.markdown("## 📊 Well Log Viewer")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload LAS files in **📁 Data Upload** first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)

        df_v = well.df.copy() if (well.df is not None and not well.df.empty) \
               else pd.DataFrame({c: well.curves[c].array for c in well.curves})
        if "DEPTH" not in df_v.columns and "DEPT" not in df_v.columns:
            df_v.insert(0, "DEPTH", well.get_depth())
        dc = _depth_col(df_v)

        d_min = float(df_v[dc].min()); d_max = float(df_v[dc].max())
        raw_c = [c for c in well.curves if c not in ("DEPT","DEPTH","MD")]
        der_c = [c for c in ["VSHALE","PHIE","PHID","SW","SH","PERM_mD","PORE_PRESS_PSI"]
                 if c in df_v.columns]
        all_c = raw_c + [c for c in der_c if c not in raw_c]

        ctrl, plot_col = st.columns([1, 4])
        with ctrl:
            sel = st.multiselect("Curves", all_c,
                                  default=[c for c in ["GR","RHOB","NPHI","RT"] if c in all_c])
            st.markdown("**Depth Window**")
            z_top  = st.number_input("Top (m)",  value=d_min, step=10.0,
                                      min_value=d_min, max_value=d_max)
            z_base = st.number_input("Base (m)", value=d_max, step=10.0,
                                      min_value=d_min, max_value=d_max)
            if z_top >= z_base: z_base = z_top + 10.0
            show_zones = st.checkbox("Show interpreted zones", True)
            show_owc   = st.checkbox("Show fluid contact",     True)

        with plot_col:
            df_z = _filter_depth(df_v, dc, z_top, z_base)
            zones_ov, owc_l = [], None
            if show_zones or show_owc:
                res = ss("reservoirs",[])
                rm  = next((r for r in res if r.well_name == chosen), None)
                if rm:
                    if show_zones: zones_ov = rm.zones
                    if show_owc:   owc_l    = rm.fluid_contact
            if sel:
                st.pyplot(make_log_plot(df_z, sel, dc,
                                         title=f"{chosen}  [{z_top:.0f}–{z_base:.0f} m]",
                                         zones=zones_ov, owc_depth=owc_l),
                          use_container_width=True)
                if owc_l:
                    st.markdown(f'<span style="color:#42a5f5">── Fluid contact: <b>{owc_l:.1f} m</b></span>',
                                unsafe_allow_html=True)
            else:
                st.info("Select at least one curve.")

        if "FACIES" in df_z.columns:
            st.markdown("**Facies Track**")
            st.pyplot(make_facies_track(df_z[dc].values, df_z["FACIES"].values),
                      use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: LOG COMPARISON  (proper side-by-side)
# ════════════════════════════════════════════════════════════
elif page == "🔎 Log Comparison":
    st.markdown("## 🔎 Side-by-Side Log Comparison")
    wells = ss("wells",[])
    if len(wells) < 2:
        st.info("Load **at least 2 wells** to compare them.")
    else:
        wnames = [w.header.well_name for w in wells]
        c1, c2, c3 = st.columns(3)
        name_a = c1.selectbox("Well A (Left)",  wnames, index=0)
        name_b = c2.selectbox("Well B (Right)", wnames, index=min(1,len(wnames)-1))
        sel_curves = c3.multiselect("Curves",
            ["GR","RHOB","NPHI","RT","VSHALE","PHIE","SW","PERM_mD"],
            default=["GR","RHOB","NPHI"])

        if name_a == name_b:
            st.warning("Select two different wells.")
        elif not sel_curves:
            st.info("Select at least one curve.")
        else:
            wa = next(w for w in wells if w.header.well_name == name_a)
            wb = next(w for w in wells if w.header.well_name == name_b)

            def _df(w):
                if w.df is not None and not w.df.empty: return w.df.copy()
                raw = pd.DataFrame({c: w.curves[c].array for c in w.curves})
                raw.insert(0, "DEPTH", w.get_depth()); return raw

            dfa = _df(wa); dfb = _df(wb)
            dca = _depth_col(dfa); dcb = _depth_col(dfb)

            c_top  = max(float(dfa[dca].min()), float(dfb[dcb].min()))
            c_base = min(float(dfa[dca].max()), float(dfb[dcb].max()))

            if c_top >= c_base:
                st.warning("Wells have no overlapping depth range.")
            else:
                r1, r2 = st.columns(2)
                zt = r1.number_input("Shared Top (m)",  value=c_top,  step=10.0,
                                      min_value=c_top, max_value=c_base)
                zb = r2.number_input("Shared Base (m)", value=c_base, step=10.0,
                                      min_value=c_top, max_value=c_base)
                if zt >= zb: zb = zt + 10.0

                show_z = st.checkbox("Show interpreted zones", True)
                res    = ss("reservoirs",[])
                za     = next((r.zones for r in res if r.well_name == name_a),[]) if show_z else []
                zb_z   = next((r.zones for r in res if r.well_name == name_b),[]) if show_z else []

                fig = make_comparison_plot(wa, wb, sel_curves, dfa, dfb,
                                            d_min=zt, d_max=zb,
                                            zones_a=za, zones_b=zb_z)
                st.pyplot(fig, use_container_width=True)

                # Facies legend
                all_zones = za + zb_z
                if all_zones:
                    unique_f = list({z.facies.value for z in all_zones})
                    badges = " &nbsp; ".join(
                        f'<span style="background:{FACIES_COLORS.get(f,"#37474f")};'
                        f'padding:2px 8px;border-radius:3px;font-size:.78rem">{f}</span>'
                        for f in unique_f)
                    st.markdown(f"**Zone colours:** {badges}", unsafe_allow_html=True)

                # Correlation table
                if st.checkbox("Show Pearson correlations between wells"):
                    from project_QLE.analysis import correlate_wells
                    rows = []
                    for curve in sel_curves:
                        try:
                            res_c = correlate_wells(wa, wb, curve)
                            q = ("✓ Good" if abs(res_c.pearson_r)>0.6
                                 else "△ Fair" if abs(res_c.pearson_r)>0.3 else "✗ Poor")
                            rows.append({"Curve":curve, "r":f"{res_c.pearson_r:.3f}",
                                          "Lag (m)":f"{res_c.lag_m:.1f}", "Quality":q})
                        except Exception:
                            rows.append({"Curve":curve, "r":"N/A", "Lag (m)":"N/A", "Quality":"—"})
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: PETROPHYSICS
# ════════════════════════════════════════════════════════════
elif page == "⚗️ Petrophysics":
    st.markdown("## ⚗️ Petrophysical Analysis")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload LAS files first.")
    else:
        col_cfg, col_res = st.columns([1,3])
        with col_cfg:
            chosen = st.selectbox("Well", [w.header.well_name for w in wells])
            well   = next(w for w in wells if w.header.well_name == chosen)
            bo     = ["SIRTE","GHADAMES","MURZUQ","KUFRA","OFFSHORE"]
            sel_b  = st.selectbox("Basin", bo,
                                   index=bo.index(well.header.basin) if well.header.basin in bo else 0)

            from project_QLE.core.libya_geology import get_basin_defaults
            defs = get_basin_defaults(sel_b)
            with st.expander("Parameters"):
                gr_clean   = st.number_input("GR Clean (GAPI)",  value=float(defs["gr_clean"]))
                gr_shale   = st.number_input("GR Shale (GAPI)",  value=float(defs["gr_shale"]))
                rho_matrix = st.number_input("ρ matrix (g/cc)",  value=float(defs["rho_matrix"]), step=0.01)
                rw         = st.number_input("Rw (ohm-m)",       value=float(defs["rw"]), step=0.001, format="%.3f")

            if st.button("▶ Run Petrophysics", use_container_width=True, type="primary"):
                with st.spinner("Computing …"):
                    try:
                        from project_QLE.analysis import PetrophysicsEngine
                        df_p = PetrophysicsEngine(well, basin=sel_b,
                                                    gr_clean=gr_clean, gr_shale=gr_shale,
                                                    rho_matrix=rho_matrix, rw=rw).run()
                        well.df = df_p
                        for i,w in enumerate(wells):
                            if w.header.well_name == chosen:
                                st.session_state["wells"][i] = well
                        st.session_state[f"petro_{chosen}"] = df_p
                        st.success("✓ Petrophysics complete")
                    except Exception as e:
                        st.error(str(e))

        with col_res:
            key = f"petro_{chosen}"
            if key not in st.session_state:
                st.info("Click **▶ Run Petrophysics**")
            else:
                df_p = st.session_state[key]
                dc   = _depth_col(df_p)
                d_mn = float(df_p[dc].min()); d_mx = float(df_p[dc].max())

                m = {"Avg PHIE":(f"{df_p['PHIE'].mean()*100:.1f}%" if 'PHIE' in df_p.columns else "N/A","Porosity"),
                     "Avg Sw"  :(f"{df_p['SW'].mean()*100:.1f}%"   if 'SW'   in df_p.columns else "N/A","Water Sat"),
                     "Avg Vsh" :(f"{df_p['VSHALE'].mean()*100:.1f}%" if 'VSHALE' in df_p.columns else "N/A","Vshale"),
                     "Avg k"   :(f"{df_p['PERM_mD'].mean():.1f} mD"  if 'PERM_mD' in df_p.columns else "N/A","Perm")}
                cols = st.columns(4)
                for col,(lbl,(val,sub)) in zip(cols,m.items()):
                    col.markdown(_mc(lbl,val,sub), unsafe_allow_html=True)

                pz1,pz2 = st.columns(2)
                pz_top  = pz1.number_input("View Top (m)",  value=d_mn, step=10.0, min_value=d_mn, max_value=d_mx)
                pz_base = pz2.number_input("View Base (m)", value=d_mx, step=10.0, min_value=d_mn, max_value=d_mx)
                df_pz   = _filter_depth(df_p, dc, pz_top, pz_base)

                t1,t2,t3 = st.tabs(["📉 Derived Logs","⬡ Crossplots","📋 Data Table"])
                with t1:
                    der = [c for c in ["GR","VSHALE","PHIE","SW","SH","PERM_mD","PORE_PRESS_PSI"] if c in df_pz.columns]
                    st.pyplot(make_log_plot(df_pz, der, dc, f"{chosen} Derived [{pz_top:.0f}–{pz_base:.0f} m]"),
                              use_container_width=True)
                with t2:
                    c1,c2 = st.columns(2)
                    if "RHOB" in df_p.columns and "NPHI" in df_p.columns:
                        c1.pyplot(make_crossplot(df_p,"NPHI","RHOB","VSHALE","N-D Crossplot"),
                                  use_container_width=True)
                    if "PHIE" in df_p.columns and "PERM_mD" in df_p.columns:
                        c2.pyplot(make_crossplot(df_p,"PHIE","PERM_mD","SW","Porosity–Perm"),
                                  use_container_width=True)
                with t3:
                    st.dataframe(df_p.round(4), use_container_width=True)
                    st.download_button("⬇ Download CSV", df_p.to_csv(index=False).encode(),
                                       f"{chosen}_petrophysics.csv","text/csv")

# ════════════════════════════════════════════════════════════
#  PAGE: PETRO SUMMARY
# ════════════════════════════════════════════════════════════
elif page == "📊 Petro Summary":
    st.markdown("## 📊 Petrophysical Summary")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells and run Petrophysics first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)

        if well.df is None or "PHIE" not in (well.df.columns if well.df is not None else []):
            st.warning("Run **⚗️ Petrophysics** on this well first.")
        else:
            df_s = well.df.copy()
            from project_QLE.analysis.petro_summaries import (
                summarise_porosity, summarise_permeability,
                summarise_saturation, build_bundle
            )

            phi_s = summarise_porosity(df_s)
            k_s   = summarise_permeability(df_s)
            sat_s = summarise_saturation(df_s)

            st.markdown("### Porosity")
            if phi_s:
                cols = st.columns(4)
                for col, (lbl,val) in zip(cols, [
                    ("Mean φ",f"{phi_s.mean:.1%}"),
                    ("P50",   f"{phi_s.p50:.1%}"),
                    ("Net Pay",f"{phi_s.net_pay_m:.1f} m"),
                    ("Quality",phi_s.quality),
                ]):
                    badge = QUALITY_BADGE.get(phi_s.quality, "badge-fair") if lbl=="Quality" else None
                    v = f'<span class="{badge}">{val}</span>' if badge else val
                    col.markdown(_mc(lbl, v, ""), unsafe_allow_html=True)

                st.pyplot(make_histogram(df_s["PHIE"].values.astype(float),
                                          "Porosity (PHIE) Distribution",
                                          color="#00bcd4", units="PHIE"),
                          use_container_width=True)

            st.markdown("### Permeability")
            if k_s:
                cols = st.columns(4)
                for col, (lbl,val) in zip(cols, [
                    ("Mean k",f"{k_s.mean_md:.1f} mD"),
                    ("P50",   f"{k_s.p50_md:.1f} mD"),
                    ("Geom. Mean",f"{k_s.log_mean_md:.1f} mD"),
                    ("Quality",k_s.quality),
                ]):
                    badge = QUALITY_BADGE.get(k_s.quality, "badge-fair") if lbl=="Quality" else None
                    v = f'<span class="{badge}">{val}</span>' if badge else val
                    col.markdown(_mc(lbl, v, ""), unsafe_allow_html=True)

                log_k = np.log10(df_s["PERM_mD"].dropna().values)
                log_k = log_k[np.isfinite(log_k)]
                st.pyplot(make_histogram(log_k, "Permeability Distribution (log₁₀ mD)",
                                          color="#f44336", units="log₁₀(k mD)"),
                          use_container_width=True)

            st.markdown("### Saturation")
            if sat_s:
                cols = st.columns(4)
                for col, (lbl,val) in zip(cols, [
                    ("Sw Mean",f"{sat_s.sw_mean:.1%}"),
                    ("Sh Mean",f"{sat_s.sh_mean:.1%}"),
                    ("So Est.",f"{sat_s.so_mean:.1%}"),
                    ("Fluid",  sat_s.fluid_type),
                ]):
                    col.markdown(_mc(lbl, val, ""), unsafe_allow_html=True)

                # Saturation pie
                fig, ax = plt.subplots(figsize=(5,4))
                fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_BG)
                vals   = [sat_s.sw_mean, sat_s.so_mean, max(sat_s.sg_mean,0)]
                labels = ["Water","Oil","Gas"]
                colors = ["#42a5f5","#ffb300","#ef5350"]
                non_z  = [(v,l,c) for v,l,c in zip(vals,labels,colors) if v>0.001]
                if non_z:
                    vv,ll,cc = zip(*non_z)
                    ax.pie(vv, labels=ll, colors=cc, autopct="%1.1f%%",
                           textprops={"color":"#e0e8f0","fontsize":9})
                ax.set_title("Saturation Distribution", color="#4fc3f7")
                st.pyplot(fig, use_container_width=True)

            # Full text summary
            st.markdown("### Summary Description")
            bundle = build_bundle(chosen, well.header.basin or basin, df_s)
            _gb(bundle.description)

            # Crossplots for sandstone analysis
            st.markdown("### Petrophysical Crossplots")
            xc1, xc2 = st.columns(2)
            if "GR" in df_s.columns and "RHOB" in df_s.columns:
                xc1.pyplot(make_crossplot(df_s,"GR","RHOB","VSHALE","GR vs RHOB"),
                           use_container_width=True)
            if "SW" in df_s.columns and "PHIE" in df_s.columns:
                xc2.pyplot(make_crossplot(df_s,"PHIE","SW","VSHALE","Porosity–Sw"),
                           use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: FACIES ANALYSIS
# ════════════════════════════════════════════════════════════
elif page == "🪨 Facies Analysis":
    st.markdown("## 🪨 Facies Analysis")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells first.")
    else:
        col_cfg, col_out = st.columns([1,3])
        with col_cfg:
            chosen = st.selectbox("Well", [w.header.well_name for w in wells])
            well   = next(w for w in wells if w.header.well_name == chosen)
            method = st.radio("Method", ["KMeans (Unsupervised)","Rule-Based (GR/RHOB)"])
            n_clust= st.slider("KMeans Clusters", 3, 8, 5) if "KMeans" in method else 5

            if st.button("▶ Classify Facies", use_container_width=True, type="primary"):
                df_src = well.df if well.df is not None else pd.DataFrame(
                    {c: well.curves[c].array for c in well.curves})
                if df_src.empty:
                    st.error("Run Petrophysics first.")
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
                        for i,w in enumerate(wells):
                            if w.header.well_name == chosen:
                                st.session_state["wells"][i] = well
                        st.success(f"✓ {len(zones)} zones")
                    except Exception as e:
                        st.error(str(e))

        with col_out:
            key = f"facies_{chosen}"
            if key not in st.session_state:
                st.info("Click **▶ Classify Facies**")
            else:
                labels, zones, df_f = st.session_state[key]
                dc = _depth_col(df_f)
                unique, counts = np.unique(labels, return_counts=True)

                d_mn = float(df_f[dc].min()); d_mx = float(df_f[dc].max())
                r1,r2 = st.columns(2)
                fz_top  = r1.number_input("View Top (m)",  value=d_mn, step=10.0,
                                           min_value=d_mn, max_value=d_mx, key="fz_t")
                fz_base = r2.number_input("View Base (m)", value=d_mx, step=10.0,
                                           min_value=d_mn, max_value=d_mx, key="fz_b")
                df_fz = _filter_depth(df_f, dc, fz_top, fz_base)

                c1,c2 = st.columns(2)
                with c1:
                    fig, ax = plt.subplots(figsize=(4.5,4.5))
                    fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_BG)
                    ax.pie(counts, labels=unique,
                           colors=[FACIES_COLORS.get(u,"#78909c") for u in unique],
                           autopct="%1.0f%%", startangle=90,
                           textprops={"color":"#e0e8f0","fontsize":8})
                    ax.set_title("Facies Distribution", color="#4fc3f7")
                    st.pyplot(fig, use_container_width=True)
                with c2:
                    st.pyplot(make_facies_track(df_fz[dc].values, df_fz["FACIES"].values),
                              use_container_width=True)

                if "GR" in df_fz.columns:
                    gr_curves = [c for c in ["GR","RHOB","NPHI"] if c in df_fz.columns]
                    st.pyplot(make_log_plot(df_fz, gr_curves, dc,
                                            f"{chosen} [{fz_top:.0f}–{fz_base:.0f} m]",
                                            zones=zones),
                              use_container_width=True)

                st.dataframe(pd.DataFrame([{
                    "Top (m)":z.top, "Base (m)":z.base,
                    "Thickness (m)":round(z.base-z.top,1), "Facies":z.facies.value
                } for z in zones]), use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: STATISTICS
# ════════════════════════════════════════════════════════════
elif page == "📈 Statistics":
    st.markdown("## 📈 Statistical Analysis")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)
        df_st  = (well.df if (well.df is not None and not well.df.empty)
                  else pd.DataFrame({c: well.curves[c].array for c in well.curves}))
        num_c  = [c for c in df_st.columns
                  if pd.api.types.is_numeric_dtype(df_st[c])
                  and c not in ("DEPTH","DEPT","MD")]

        t1,t2,t3,t4 = st.tabs(["📊 Descriptive","📉 Histograms","🔥 Correlation Matrix","🎲 Monte Carlo"])
        with t1:
            from project_QLE.analysis import batch_stats
            stats_list = batch_stats(well, num_c[:12])
            if stats_list:
                st.dataframe(pd.DataFrame([{
                    "Curve":s.curve,"N":s.n,
                    "Mean":f"{s.mean:.3f}","Std":f"{s.std:.3f}",
                    "Min":f"{s.min_val:.3f}","Max":f"{s.max_val:.3f}",
                    "P10":f"{s.p10:.3f}","P50":f"{s.p50:.3f}","P90":f"{s.p90:.3f}",
                    "Skew":f"{s.skewness:.2f}",
                } for s in stats_list]), use_container_width=True)
        with t2:
            sel_h = st.selectbox("Curve", num_c)
            if sel_h:
                st.pyplot(make_histogram(df_st[sel_h].values.astype(float),
                                          sel_h, units=sel_h), use_container_width=True)
        with t3:
            from project_QLE.analysis import pearson_matrix
            cc = st.multiselect("Curves",
                                 [c for c in num_c if df_st[c].notna().sum()>10],
                                 default=num_c[:6])
            if len(cc) >= 2:
                corr = pearson_matrix(df_st, cc)
                fig, ax = plt.subplots(figsize=(7,6))
                fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_BG)
                im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
                ax.set_xticks(range(len(cc))); ax.set_xticklabels(cc, rotation=45, color=TICK_CLR, fontsize=8)
                ax.set_yticks(range(len(cc))); ax.set_yticklabels(cc, color=TICK_CLR, fontsize=8)
                for i in range(len(cc)):
                    for j in range(len(cc)):
                        ax.text(j,i,f"{corr.values[i,j]:.2f}",ha="center",va="center",fontsize=7,color="white")
                plt.colorbar(im,ax=ax); ax.set_title("Pearson Correlation Matrix",color="#4fc3f7")
                st.pyplot(fig, use_container_width=True)
        with t4:
            from project_QLE.analysis import monte_carlo_porosity
            c1,c2 = st.columns(2)
            pm = c1.number_input("Mean φ", 0.0, 0.5, 0.15, step=0.01)
            ps = c2.number_input("Std",    0.001, 0.2, 0.04, step=0.005)
            nm = st.slider("Samples", 1000, 50000, 10000, 1000)
            mc_r = monte_carlo_porosity(pm, ps, nm)
            c1.metric("P10",f"{mc_r['p10']*100:.1f}%"); c2.metric("P50",f"{mc_r['p50']*100:.1f}%")
            c1.metric("P90",f"{mc_r['p90']*100:.1f}%")
            edges = np.array(mc_r["histogram"]["edges"]); counts = np.array(mc_r["histogram"]["counts"])
            fig, ax = plt.subplots(figsize=(5,3))
            fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
            ax.bar(edges[:-1], counts, width=np.diff(edges), color="#4fc3f7", alpha=0.8)
            for p,v in [("P10",mc_r["p10"]),("P50",mc_r["p50"]),("P90",mc_r["p90"])]:
                ax.axvline(v, color="#ff9800", lw=1.5, ls="--", label=f"{p}={v*100:.1f}%")
            ax.legend(fontsize=8,labelcolor=TICK_CLR,facecolor=DARK_BG)
            ax.set_xlabel("Porosity",color=TICK_CLR); ax.set_ylabel("Count",color=TICK_CLR)
            ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
            ax.set_title("MC Porosity Distribution",color="#4fc3f7")
            st.pyplot(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: LOG CORRELATION
# ════════════════════════════════════════════════════════════
elif page == "🔗 Log Correlation":
    st.markdown("## 🔗 Cross-Well Log Correlation")
    wells = ss("wells",[])
    if len(wells) < 2:
        st.info("Load **2 or more wells** to run correlation.")
    else:
        curve = st.selectbox("Correlation Curve",["GR","RHOB","NPHI","RT","PHIE","SW"])
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
            st.dataframe(pd.DataFrame([{
                "Well A":r.well_a,"Well B":r.well_b,"Curve":r.curve,
                "Pearson r":f"{r.pearson_r:.3f}","Lag (m)":f"{r.lag_m:.1f}",
                "Quality":("✓ Good" if abs(r.pearson_r)>0.6
                            else "△ Fair" if abs(r.pearson_r)>0.3 else "✗ Poor")
            } for r in results]), use_container_width=True)
            if tops_df is not None and not tops_df.empty:
                st.markdown("**Formation Tops (auto-picked)**")
                st.dataframe(tops_df.round(1), use_container_width=True)
            st.markdown("**GR Overlay**")
            fig,ax = plt.subplots(figsize=(10,5))
            fig.patch.set_facecolor(DARK_BG); ax.set_facecolor(DARK_AX)
            cmap = plt.get_cmap("tab10")
            for i,w in enumerate(wells):
                gr=w.get_curve("GR"); depth=w.get_depth()
                if gr is not None and depth is not None:
                    ax.plot(depth, gr, color=cmap(i), lw=0.8, label=w.header.well_name, alpha=0.85)
            ax.set_xlabel("Depth (m)",color=TICK_CLR); ax.set_ylabel("GR (GAPI)",color=TICK_CLR)
            ax.legend(fontsize=8,labelcolor=TICK_CLR,facecolor=DARK_BG)
            ax.tick_params(colors=TICK_CLR); ax.spines[:].set_color(DARK_GRID)
            ax.grid(color=DARK_GRID,lw=0.4,alpha=0.5); ax.set_title("GR Log Overlay",color="#4fc3f7")
            st.pyplot(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: RESERVOIR SUMMARY
# ════════════════════════════════════════════════════════════
elif page == "🏭 Reservoir Summary":
    st.markdown("## 🏭 Reservoir Characterisation")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells first.")
    else:
        if st.button("▶ Build Reservoir Summaries", type="primary", use_container_width=True):
            from project_QLE.analysis import (PetrophysicsEngine, KMeansFacies,
                                               labels_to_zones, build_reservoir_summary)
            summaries = []
            prog = st.progress(0)
            for i,well in enumerate(wells):
                prog.progress((i+1)/len(wells), well.header.well_name)
                try:
                    if well.df is None or "PHIE" not in (well.df.columns if well.df is not None else []):
                        well.df = PetrophysicsEngine(well, basin=well.header.basin).run()
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
            st.success(f"✓ {len(summaries)} summaries built")

        if "reservoirs" in st.session_state:
            from project_QLE.analysis.reservoir import stoiip_bbl, giip_mscf
            summaries = st.session_state["reservoirs"]
            st.dataframe(pd.DataFrame([{
                "Well":rs.well_name, "Basin":rs.basin,
                "Net Pay (m)":f"{rs.net_pay_m:.1f}" if rs.net_pay_m else "N/A",
                "φ avg":f"{rs.avg_porosity:.3f}" if rs.avg_porosity else "N/A",
                "Sw avg":f"{rs.avg_sw:.3f}" if rs.avg_sw else "N/A",
                "k avg (mD)":f"{rs.avg_perm_mD:.1f}" if rs.avg_perm_mD else "N/A",
                "OWC (m)":f"{rs.fluid_contact:.1f}" if rs.fluid_contact else "—",
            } for rs in summaries]), use_container_width=True)

            v1,v2,v3 = st.columns(3)
            area = v1.number_input("Area (acres)", 100, 50000, 5000, 100)
            bo   = v2.number_input("Bo (res bbl/STB)", 1.0, 2.0, 1.2, 0.05)
            bg   = v3.number_input("Bg (res ft³/SCF)", 0.001, 0.02, 0.005, 0.001, format="%.3f")
            for rs in summaries:
                if rs.net_pay_m and rs.avg_porosity and rs.avg_sw:
                    net_ft = rs.net_pay_m * 3.28084
                    vc1,vc2 = st.columns(2)
                    vc1.metric(f"STOIIP – {rs.well_name}",
                               f"{stoiip_bbl(area,net_ft,rs.avg_porosity,rs.avg_sw,bo)/1e6:.2f} MMSTB")
                    vc2.metric(f"GIIP – {rs.well_name}",
                               f"{giip_mscf(area,net_ft,rs.avg_porosity,rs.avg_sw,bg)/1e6:.2f} Bscf")

# ════════════════════════════════════════════════════════════
#  PAGE: FORMATION TOPS
# ════════════════════════════════════════════════════════════
elif page == "🗻 Formation Tops":
    st.markdown("## 🗻 Formation Tops & Lithology")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)

        key = f"tops_{chosen}"
        ss(key, [])

        t1, t2 = st.tabs(["📍 Pick Tops", "📋 Top Table & Descriptions"])

        with t1:
            st.markdown('<div class="sh">Add a Formation Top</div>', unsafe_allow_html=True)
            fc1,fc2,fc3 = st.columns(3)
            f_name  = fc1.text_input("Formation Name", placeholder="e.g. Intisar Carbonate")
            f_depth = fc2.number_input("Top Depth (m)", value=2000.0, step=1.0)
            f_base  = fc3.number_input("Base Depth (m)", value=2050.0, step=1.0)

            fc4,fc5 = st.columns(2)
            f_litho = fc4.selectbox("Lithology",
                                     ["Sandstone","Shale","Limestone","Dolomite","Anhydrite","Unknown"])
            f_desc  = fc5.text_area("Notes / Description", height=60)

            if st.button("➕ Add Formation Top", type="primary"):
                if f_name and f_depth < f_base:
                    df_p = well.df
                    avg_phi = None; avg_k = None
                    if df_p is not None:
                        dc = _depth_col(df_p)
                        seg = df_p[(df_p[dc]>=f_depth) & (df_p[dc]<=f_base)]
                        if "PHIE" in seg.columns: avg_phi = float(seg["PHIE"].mean())
                        if "PERM_mD" in seg.columns: avg_k = float(seg["PERM_mD"].mean())

                    from project_QLE.analysis.petro_summaries import describe_formation
                    auto_desc = describe_formation(f_name, f_litho, f_depth, f_base, avg_phi, avg_k)

                    tops = st.session_state[key]
                    tops.append({
                        "formation_name": f_name,
                        "depth_m":  f_depth,
                        "base_m":   f_base,
                        "lithology": f_litho,
                        "description": f_desc or auto_desc,
                        "avg_phi":  avg_phi,
                        "avg_k":    avg_k,
                    })
                    st.session_state[key] = tops
                    st.success(f"✓ Added: {f_name} @ {f_depth:.1f} m")

                    # Optionally save to DB
                    try:
                        from project_QLE.database import save_formation_top
                        from project_QLE.database.db import get_session, Well as DBWell
                        sess = get_session()
                        db_well = sess.query(DBWell).filter_by(well_name=chosen).first()
                        if db_well:
                            save_formation_top(db_well.id, f_name, f_depth, f_litho, f_desc or auto_desc)
                        sess.close()
                    except Exception:
                        pass
                else:
                    st.warning("Fill formation name and ensure Top < Base.")

            # Show tops on log
            tops_list = st.session_state[key]
            if tops_list and well.df is not None:
                df_v = well.df
                dc_v = _depth_col(df_v)
                gr_curves = [c for c in ["GR","RHOB","NPHI"] if c in df_v.columns]
                if gr_curves:
                    fig = make_log_plot(df_v, gr_curves, dc_v, f"{chosen} – Formation Tops")
                    for top in tops_list:
                        for ax in fig.axes:
                            ax.axhline(top["depth_m"], color="#ffb300", lw=1.2,
                                        ls="--", alpha=0.9, zorder=10)
                            ax.text(ax.get_xlim()[0], top["depth_m"],
                                    f" {top['formation_name']}", fontsize=6,
                                    color="#ffb300", va="bottom")
                    st.pyplot(fig, use_container_width=True)

        with t2:
            tops_list = st.session_state[key]
            if not tops_list:
                st.info("No tops added yet. Use the 'Pick Tops' tab.")
            else:
                st.dataframe(pd.DataFrame([{
                    "Formation": t["formation_name"],
                    "Top (m)": t["depth_m"], "Base (m)": t["base_m"],
                    "Thickness (m)": round(t["base_m"]-t["depth_m"],1),
                    "Lithology": t["lithology"],
                    "Avg φ": f"{t['avg_phi']:.1%}" if t.get("avg_phi") else "N/A",
                    "Avg k (mD)": f"{t['avg_k']:.1f}" if t.get("avg_k") else "N/A",
                } for t in tops_list]), use_container_width=True)

                st.markdown("### Lithology Descriptions")
                for top in tops_list:
                    with st.expander(f"📍 {top['formation_name']}  ({top['lithology']})"):
                        _gb(top["description"])
                        if top.get("avg_phi"):
                            st.metric("Avg Porosity", f"{top['avg_phi']:.1%}")
                        if top.get("avg_k"):
                            st.metric("Avg Permeability", f"{top['avg_k']:.1f} mD")

# ════════════════════════════════════════════════════════════
#  PAGE: DST TESTS
# ════════════════════════════════════════════════════════════
elif page == "🔬 DST Tests":
    st.markdown("## 🔬 Drill Stem Test (DST) Data")
    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        key    = f"dst_{chosen}"
        ss(key, [])

        t1, t2 = st.tabs(["➕ Add DST Test", "📋 DST Summary"])

        with t1:
            st.markdown('<div class="sh">Enter DST Test Parameters</div>', unsafe_allow_html=True)
            r1c1,r1c2,r1c3 = st.columns(3)
            d_name    = r1c1.text_input("Test Name", placeholder="e.g. DST-1 Main Sand")
            d_depth   = r1c2.number_input("Test Depth (m)", value=2000.0, step=1.0)
            d_fluid   = r1c3.selectbox("Fluid Type", ["Oil","Gas","Water","Mixed"])

            r2c1,r2c2,r2c3 = st.columns(3)
            d_isip    = r2c1.number_input("Initial SICP (psi)", value=0.0, step=10.0)
            d_fsip    = r2c2.number_input("Final SICP (psi)",   value=0.0, step=10.0)
            d_rate    = r2c3.number_input("Flow Rate (bpd)",    value=0.0, step=10.0)

            r3c1,r3c2,r3c3 = st.columns(3)
            d_perm    = r3c1.number_input("Perm from test (mD)", value=0.0, step=0.1, format="%.2f")
            d_skin    = r3c2.number_input("Skin Factor",         value=0.0, step=0.5)
            d_rp      = r3c3.number_input("Reservoir P (psi)",   value=0.0, step=10.0)

            r4c1,r4c2 = st.columns(2)
            d_gor     = r4c1.number_input("GOR (scf/bbl)",   value=0.0, step=10.0)
            d_api     = r4c2.number_input("API Gravity",      value=0.0, step=0.5)

            if st.button("➕ Add DST Test", type="primary") and d_name:
                test = {
                    "test_name": d_name, "depth_m": d_depth, "fluid_type": d_fluid,
                    "initial_shut_in_psi": d_isip or None,
                    "final_shut_in_psi":   d_fsip or None,
                    "flow_rate_bpd":  d_rate or None,
                    "permeability_md": d_perm or None,
                    "skin_factor": d_skin,
                    "reservoir_pressure_psi": d_rp or None,
                    "gor_scfbbl": d_gor or None,
                    "api_gravity": d_api or None,
                }
                tests = st.session_state[key]
                tests.append(test)
                st.session_state[key] = tests
                st.success(f"✓ Added DST: {d_name}")

        with t2:
            tests = st.session_state[key]
            if not tests:
                st.info("No DST tests added yet.")
            else:
                from project_QLE.analysis.petro_summaries import interpret_dst
                for t in tests:
                    with st.expander(f"🔬 {t['test_name']}  @  {t['depth_m']:.1f} m"):
                        _gb(interpret_dst(t))
                        c1,c2,c3 = st.columns(3)
                        if t.get("flow_rate_bpd"):
                            c1.metric("Flow Rate", f"{t['flow_rate_bpd']:.0f} bpd")
                        if t.get("permeability_md"):
                            c2.metric("Permeability", f"{t['permeability_md']:.1f} mD")
                        if t.get("reservoir_pressure_psi"):
                            c3.metric("Reservoir P", f"{t['reservoir_pressure_psi']:.0f} psi")

                # DST summary table
                st.dataframe(pd.DataFrame([{
                    "Test": t["test_name"], "Depth (m)": t["depth_m"],
                    "Fluid": t["fluid_type"],
                    "Rate (bpd)": t.get("flow_rate_bpd","—"),
                    "k (mD)": t.get("permeability_md","—"),
                    "Skin": t.get("skin_factor","—"),
                    "Res. P (psi)": t.get("reservoir_pressure_psi","—"),
                } for t in tests]), use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: ML MODEL COMPARISON
# ════════════════════════════════════════════════════════════
elif page == "🤖 ML Comparison":
    st.markdown("## 🤖 ML Model Comparison")
    st.markdown("Train **Linear Regression**, **Random Forest**, and **XGBoost** on your well data "
                "and compare their performance for predicting petrophysical properties.")
    st.divider()

    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells and run Petrophysics first.")
    else:
        chosen = st.selectbox("Well", [w.header.well_name for w in wells])
        well   = next(w for w in wells if w.header.well_name == chosen)

        if well.df is None or "PHIE" not in (well.df.columns if well.df is not None else []):
            st.warning("Run **⚗️ Petrophysics** on this well first.")
        else:
            df_ml = well.df.copy()
            num_cols = [c for c in df_ml.columns
                        if pd.api.types.is_numeric_dtype(df_ml[c])
                        and c not in ("DEPTH","DEPT","MD")]

            col_cfg, col_res = st.columns([1, 2])
            with col_cfg:
                target   = st.selectbox("Target Variable (predict)",
                                         [c for c in ["PHIE","PERM_mD","SW","VSHALE"] if c in df_ml.columns])
                features = st.multiselect("Input Features",
                                           [c for c in num_cols if c != target],
                                           default=[c for c in ["GR","RHOB","NPHI","RT"] if c in df_ml.columns])
                test_pct = st.slider("Test set %", 10, 40, 20)
                n_trees  = st.slider("RF/XGB Trees", 50, 500, 100, 50)

                if st.button("▶ Train & Compare Models", type="primary", use_container_width=True):
                    if not features:
                        st.error("Select at least one input feature.")
                    else:
                        with st.spinner("Training all models …"):
                            try:
                                from project_QLE.ml import ModelComparer
                                mc = ModelComparer(df_ml, target=target,
                                                    features=features,
                                                    test_size=test_pct/100)
                                mc.train_linear_regression()
                                mc.train_random_forest(n_estimators=n_trees)
                                mc.train_xgboost(n_estimators=n_trees)
                                cmp = mc.train_all_models()
                                st.session_state[f"ml_cmp_{chosen}"] = (mc, cmp, target, features)
                                st.success(f"✓ Best model: {cmp.best_model_name}  "
                                           f"(R²={float(cmp.best_result['r2']):.3f})")
                            except Exception as e:
                                st.error(str(e))

            with col_res:
                mk = f"ml_cmp_{chosen}"
                if mk not in st.session_state:
                    st.info("Configure and click ▶ Train & Compare Models")
                else:
                    mc, cmp, target_used, feat_used = st.session_state[mk]

                    # ── Comparison table ──────────────────────
                    st.markdown("### Model Performance Comparison")
                    summary = cmp.summary_df()
                    st.dataframe(summary, use_container_width=True, hide_index=True)

                    # Highlight best
                    best = cmp.best_model_name
                    r2   = float(cmp.best_result["r2"])
                    mae  = float(cmp.best_result["mae"])
                    rmse = float(cmp.best_result["rmse"])

                    bc1,bc2,bc3,bc4 = st.columns(4)
                    bc1.markdown(_mc("Best Model", best.replace("_"," ").title(), ""), unsafe_allow_html=True)
                    bc2.markdown(_mc("R² Score", f"{r2:.4f}", "higher is better"), unsafe_allow_html=True)
                    bc3.markdown(_mc("MAE", f"{mae:.4f}", "lower is better"), unsafe_allow_html=True)
                    bc4.markdown(_mc("RMSE", f"{rmse:.4f}", "lower is better"), unsafe_allow_html=True)

                    # ── Bar chart comparison ──────────────────
                    fig, axes = plt.subplots(1, 3, figsize=(10, 4))
                    fig.patch.set_facecolor(DARK_BG)
                    model_names = list(cmp.results.keys())
                    colors_bar  = ["#4fc3f7","#66bb6a","#ff7043"][:len(model_names)]

                    for ax, metric, lbl in zip(axes, ["r2","mae","rmse"],
                                                ["R² (higher better)","MAE (lower better)","RMSE (lower better)"]):
                        vals_bar = [cmp.results[m][metric] for m in model_names]
                        _style_ax(ax); ax.set_facecolor(DARK_AX)
                        bars = ax.bar([m.replace("_","\n") for m in model_names],
                                       vals_bar, color=colors_bar, alpha=0.85)
                        for bar, v in zip(bars, vals_bar):
                            ax.text(bar.get_x()+bar.get_width()/2., bar.get_height(),
                                    f"{v:.3f}", ha="center", va="bottom",
                                    fontsize=7, color=TICK_CLR)
                        ax.set_title(lbl, color="#4fc3f7", fontsize=8)
                        ax.tick_params(colors=TICK_CLR, labelsize=7)
                        ax.spines[:].set_color(DARK_GRID)
                    plt.tight_layout(); st.pyplot(fig, use_container_width=True)

                    # ── Feature importance (RF) ───────────────
                    if "random_forest" in cmp.models:
                        rf  = cmp.models["random_forest"]
                        imp = pd.Series(rf.feature_importances_, index=feat_used).sort_values(ascending=True)
                        fig2, ax2 = plt.subplots(figsize=(6, max(3, len(feat_used)*0.5)))
                        fig2.patch.set_facecolor(DARK_BG); ax2.set_facecolor(DARK_AX)
                        ax2.barh(imp.index, imp.values, color="#66bb6a", alpha=0.85)
                        ax2.set_title(f"Random Forest — Feature Importance ({target_used})",
                                      color="#4fc3f7", fontsize=9)
                        ax2.tick_params(colors=TICK_CLR, labelsize=8)
                        ax2.spines[:].set_color(DARK_GRID)
                        plt.tight_layout(); st.pyplot(fig2, use_container_width=True)

                    # ── Predict at custom depth ───────────────
                    st.markdown("### Predict at Custom Values")
                    pred_inputs = {}
                    pin_cols = st.columns(min(4, len(feat_used)))
                    for col, feat in zip(pin_cols, feat_used):
                        if feat in df_ml.columns:
                            med = float(df_ml[feat].median())
                            pred_inputs[feat] = col.number_input(f"{feat}", value=round(med,3),
                                                                   step=0.01, key=f"pred_{feat}")
                    if st.button("🔮 Predict", key="predict_btn"):
                        from project_QLE.ml import ModelComparer
                        from project_QLE.ml.model_comparison import predict_with_model
                        pcols = st.columns(len(cmp.models))
                        for col_p, (mname, _) in zip(pcols, cmp.models.items()):
                            try:
                                pred = predict_with_model(cmp.models[mname], pred_inputs)
                                col_p.metric(mname.replace("_"," ").title(), f"{pred:.4f}")
                            except Exception:
                                col_p.metric(mname.replace("_"," ").title(), "Error")

# ════════════════════════════════════════════════════════════
#  PAGE: TREND ANALYSIS
# ════════════════════════════════════════════════════════════
elif page == "📉 Trend Analysis":
    st.markdown("## 📉 Depth Trend Analysis")
    st.markdown("Fit depth-based trends using **Linear Regression** and **XGBoost** to understand "
                "how properties change with depth.")
    st.divider()

    wells = ss("wells",[])
    if not wells:
        st.info("Upload wells and run Petrophysics first.")
    else:
        chosen  = st.selectbox("Well", [w.header.well_name for w in wells])
        well    = next(w for w in wells if w.header.well_name == chosen)

        if well.df is None:
            st.warning("Run Petrophysics first.")
        else:
            df_tr = well.df.copy()
            dc_tr = _depth_col(df_tr)
            num_c = [c for c in df_tr.columns
                     if pd.api.types.is_numeric_dtype(df_tr[c]) and c not in (dc_tr,)]

            col_cfg, col_out = st.columns([1, 2])
            with col_cfg:
                target_tr = st.selectbox("Property to Analyse",
                                          [c for c in ["PHIE","PERM_mD","SW","VSHALE","GR"] if c in df_tr.columns])
                n_est_tr  = st.slider("XGBoost Trees", 20, 200, 50, 10)
                test_pct_tr = st.slider("Test Set %", 10, 40, 20)

                if st.button("▶ Run Trend Analysis", type="primary", use_container_width=True):
                    with st.spinner("Fitting trend models …"):
                        try:
                            from project_QLE.ml import TrendAnalyzer
                            ta   = TrendAnalyzer(df_tr, depth_col=dc_tr,
                                                  target_col=target_tr,
                                                  test_size=test_pct_tr/100)
                            tres = ta.analyze()
                            st.session_state[f"trend_{chosen}_{target_tr}"] = (ta, tres, target_tr)
                            st.success(f"✓ Best: {tres.best_model_name}  R²={float(tres.best_result['r2_test']):.3f}")
                        except Exception as e:
                            st.error(str(e))

            with col_out:
                tkey = f"trend_{chosen}_{target_tr}"
                if tkey not in st.session_state:
                    st.info("Configure and click ▶ Run Trend Analysis")
                else:
                    ta, tres, tgt = st.session_state[tkey]

                    # Results table
                    st.markdown("### Trend Model Comparison")
                    st.dataframe(tres.to_dataframe(), use_container_width=True, hide_index=True)

                    br = tres.best_result
                    bc1,bc2,bc3 = st.columns(3)
                    bc1.markdown(_mc("Best Model", tres.best_model_name.replace("_"," ").title(),""),
                                  unsafe_allow_html=True)
                    bc2.markdown(_mc("R² (test)",  f"{br['r2_test']:.4f}",""),  unsafe_allow_html=True)
                    bc3.markdown(_mc("MAE",         f"{br['mae']:.4f}",""),     unsafe_allow_html=True)

                    # LR equation
                    if "linear_regression" in tres.results:
                        lr_r = tres.results["linear_regression"]
                        direction = "↑ increases" if lr_r["slope"] > 0 else "↓ decreases"
                        st.info(f"**Linear trend:** {target_tr} **{direction}** with depth\n\n"
                                f"Equation: `y = {lr_r['slope']:.6f} × depth + {lr_r['intercept']:.2f}`")

                    # Plot actual vs fitted
                    depth_full = df_tr[dc_tr].values
                    vals_full  = df_tr[tgt].values.astype(float)
                    valid_mask = ~np.isnan(vals_full)

                    fig, axes = plt.subplots(1, 2, figsize=(12, 9), sharey=True)
                    fig.patch.set_facecolor(DARK_BG)

                    # Left: actual log
                    ax_act = axes[0]; _style_ax(ax_act)
                    color_t = TRACK_COLORS.get(tgt, "#78909c")
                    ax_act.plot(vals_full, depth_full, color=color_t, lw=0.8, alpha=0.85)
                    ax_act.set_xlabel(f"Actual {tgt}", color=color_t, fontsize=8, fontweight="bold")
                    ax_act.set_ylabel("Depth (m)", color=TICK_CLR, fontsize=8)
                    ax_act.tick_params(colors=TICK_CLR)
                    ax_act.set_title("Actual", color="#4fc3f7", fontsize=9)
                    ax_act.invert_yaxis()

                    # Right: model predictions overlaid
                    ax_pr = axes[1]; _style_ax(ax_pr)
                    ax_pr.plot(vals_full, depth_full, color=TICK_CLR, lw=0.5, alpha=0.4, label="Actual")

                    pred_colors = {"linear_regression":"#ffb300","xgboost":"#66bb6a"}
                    for mname, result in tres.results.items():
                        model_obj = result["model"]
                        d_input   = depth_full[valid_mask].reshape(-1,1)
                        try:
                            preds = model_obj.predict(d_input)
                            ax_pr.plot(preds, depth_full[valid_mask],
                                       color=pred_colors.get(mname,"#42a5f5"),
                                       lw=1.0, alpha=0.85,
                                       label=f"{mname.replace('_',' ').title()} (R²={result['r2_test']:.3f})")
                        except Exception:
                            pass

                    ax_pr.legend(fontsize=7, labelcolor=TICK_CLR, facecolor=DARK_BG)
                    ax_pr.set_xlabel(f"Predicted {tgt}", color="#4fc3f7", fontsize=8, fontweight="bold")
                    ax_pr.tick_params(colors=TICK_CLR)
                    ax_pr.set_title("Model Predictions", color="#4fc3f7", fontsize=9)
                    ax_pr.invert_yaxis()

                    plt.tight_layout(); st.pyplot(fig, use_container_width=True)

                    # Summary text
                    st.markdown("### Text Summary")
                    _gb(tres.summary())

# ════════════════════════════════════════════════════════════
#  PAGE: MAP VIEW
# ════════════════════════════════════════════════════════════
elif page == "🗺️ Map View":
    st.markdown("## 🗺️ Subsurface Map View")
    t1, t2 = st.tabs(["📍 Field Map","🗺️ Property Map"])
    with t1:
        from project_QLE.core.libya_geology import LIBYAN_FIELDS
        sel_b = st.multiselect("Filter Basin",["SIRTE","GHADAMES","MURZUQ","OFFSHORE"],
                                default=["SIRTE","GHADAMES","MURZUQ","OFFSHORE"])
        fdf = pd.DataFrame([f for f in LIBYAN_FIELDS if f["basin"] in sel_b])
        if not fdf.empty:
            st.map(fdf.rename(columns={"lat":"latitude","lon":"longitude"})[
                ["latitude","longitude"]], zoom=4, use_container_width=True)
            st.dataframe(fdf[["name","basin","fluid","api"]].rename(
                columns={"api":"API°","fluid":"Fluid","name":"Field","basin":"Basin"}),
                use_container_width=True)
    with t2:
        wells      = ss("wells",[])
        reservoirs = ss("reservoirs",[])
        geo_wells  = [w for w in wells if w.header.latitude and w.header.longitude]
        if len(geo_wells) < 2:
            st.info("Need ≥2 wells with LATI/LONG in LAS headers.")
        elif not reservoirs:
            st.info("Build Reservoir Summaries first.")
        else:
            prop = st.selectbox("Property",["avg_porosity","avg_sw","avg_perm_mD","net_pay_m"])
            from project_QLE.ai.map_generator import property_map
            fig = property_map(geo_wells, reservoirs, prop=prop,
                               title=f"{prop.replace('_',' ').title()} – {basin}")
            st.pyplot(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════
#  PAGE: AI INTERPRETATION
# ════════════════════════════════════════════════════════════
elif page == "🧠 AI Interpretation":
    st.markdown("## 🧠 AI Interpretation  (Gemini)")
    if not gemini_key:
        st.warning("Enter Gemini API key in the sidebar.\n\n"
                   "Get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey)")
    else:
        reservoirs  = ss("reservoirs",[])
        wells       = ss("wells",[])

        t1, t2, t3 = st.tabs(["🏭 Reservoir Narrative","🔗 Correlation","💬 Q&A"])
        with t1:
            if not reservoirs:
                st.info("Build reservoir summaries first.")
            else:
                chosen = st.selectbox("Well", [r.well_name for r in reservoirs])
                rs     = next(r for r in reservoirs if r.well_name == chosen)
                if st.button("▶ Generate Reservoir Report", type="primary"):
                    from project_QLE.analysis import batch_stats
                    wm = next((w for w in wells if w.header.well_name == chosen), None)
                    with st.spinner("Gemini interpreting …"):
                        try:
                            ai   = _get_gemini(gemini_key)
                            sts  = batch_stats(wm, ["GR","PHIE","SW","PERM_mD"]) if wm else []
                            narr = ai.interpret_reservoir(rs, sts)
                            st.session_state[f"ai_{chosen}"] = narr
                        except Exception as e:
                            st.error(str(e))
                narr = rs.ai_narrative or st.session_state.get(f"ai_{chosen}","")
                if narr: _gb(narr)

        with t2:
            corr_res = ss("corr_results",[])
            if not corr_res:
                st.info("Run Cross-Well Correlation first.")
            else:
                if st.button("▶ Generate Correlation Commentary", type="primary"):
                    with st.spinner("Analysing …"):
                        try:
                            ai   = _get_gemini(gemini_key)
                            tops = ss("corr_tops")
                            text = ai.interpret_correlations(corr_res, tops)
                            st.session_state["ai_corr"] = text
                        except Exception as e:
                            st.error(str(e))
                if "ai_corr" in st.session_state: _gb(st.session_state["ai_corr"])

        with t3:
            q = st.text_area("Geological Question", height=100,
                              placeholder="e.g. What is the typical OWC for Intisar reefs?")
            ctx = st.checkbox("Include reservoir data as context", True)
            if st.button("▶ Ask Gemini", type="primary") and q:
                ctx_txt = ""
                if ctx and reservoirs:
                    ctx_txt = "Reservoir data:\n" + "\n".join(
                        f"  {r.well_name}: net_pay={r.net_pay_m:.1f}m φ={r.avg_porosity:.3f} Sw={r.avg_sw:.3f}"
                        for r in reservoirs if r.net_pay_m)
                with st.spinner("Thinking …"):
                    try:
                        ai = _get_gemini(gemini_key)
                        _gb(ai.ask(q, ctx_txt))
                    except Exception as e:
                        st.error(str(e))

# ════════════════════════════════════════════════════════════
#  PAGE: FULL REPORT
# ════════════════════════════════════════════════════════════
elif page == "📋 Full Report":
    st.markdown("## 📋 Full Interpretation Report")

    # ⚠ project_name MUST be ABOVE the button
    project_name = st.text_input("Project Name", value="Project_QLE – Libya Exploration")
    wells        = ss("wells",[])
    reservoirs   = ss("reservoirs",[])

    if st.button("▶ Generate Full Report", type="primary", use_container_width=True):
        if not wells:
            st.warning("Load wells first.")
        else:
            from project_QLE.pipeline import QLEPipeline
            with st.spinner("Running full pipeline …"):
                try:
                    pipe = QLEPipeline(project_name=project_name or "Project_QLE",
                                       basin=basin,
                                       use_ai=bool(gemini_key),
                                       gemini_api_key=gemini_key or None)
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
        basin_display = getattr(report, "basin", basin)
        st.caption(f"Generated: {report.created_at.strftime('%Y-%m-%d %H:%M UTC')}  |  Basin: {basin_display}")

        c1,c2,c3 = st.columns(3)
        c1.metric("Wells",      len(report.wells))
        c2.metric("Reservoirs", len(report.reservoirs))
        c3.metric("Warnings",   len(report.warnings))

        if report.ai_summary:
            st.markdown('<div class="sh">AI Executive Summary</div>', unsafe_allow_html=True)
            _gb(report.ai_summary)

        for rs in report.reservoirs:
            with st.expander(f"📍 {rs.well_name}"):
                r1,r2,r3,r4 = st.columns(4)
                r1.metric("Net Pay",  f"{rs.net_pay_m:.1f} m"  if rs.net_pay_m   else "N/A")
                r2.metric("Avg φ",    f"{rs.avg_porosity:.1%}" if rs.avg_porosity else "N/A")
                r3.metric("Avg Sw",   f"{rs.avg_sw:.1%}"       if rs.avg_sw       else "N/A")
                r4.metric("Avg k",    f"{rs.avg_perm_mD:.1f} mD" if rs.avg_perm_mD else "N/A")
                if rs.ai_narrative: _gb(rs.ai_narrative)

        if report.warnings:
            with st.expander(f"⚠ {len(report.warnings)} warning(s)"):
                for w in report.warnings: st.caption(w)

        st.divider()
        if report.reservoirs:
            export_df = pd.DataFrame([{
                "Well":rs.well_name, "Basin": getattr(rs,"basin",basin),
                "Net Pay (m)":rs.net_pay_m, "Avg Porosity":rs.avg_porosity,
                "Avg Sw":rs.avg_sw, "Avg Perm (mD)":rs.avg_perm_mD,
                "OWC (m)":rs.fluid_contact,
                "AI Summary":rs.ai_narrative[:200] if rs.ai_narrative else "",
            } for rs in report.reservoirs])
            st.download_button("⬇ Export Report CSV",
                               export_df.to_csv(index=False).encode(),
                               f"ProjectQLE_{report.created_at.strftime('%Y%m%d')}.csv",
                               "text/csv", use_container_width=True)