"""
Project_QLE/ai/map_generator.py
──────────────────────────
Generate subsurface maps from well data using interpolation.

Map types
─────────
- Structure map (top / base of formation)
- Isopach (thickness)
- Porosity / permeability property maps
- Fluid saturation maps
- Seismic attribute extraction maps

Output: matplotlib figures OR plotly figures (for Streamlit phase).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # non-interactive backend for server-side generation
import matplotlib.pyplot as plt
import matplotlib.tri as mtri
from scipy.interpolate import griddata
from pathlib import Path

from project_QLE.core.models import ReservoirSummary, WellLog

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Data extraction helpers
# ─────────────────────────────────────────────

def _well_positions(wells: List[WellLog]) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Extract (x, y, name) arrays from well headers."""
    xs, ys, names = [], [], []
    for w in wells:
        x = w.header.longitude
        y = w.header.latitude
        if x is None or y is None:
            logger.warning("Well %s has no coordinates – skipped from map.", w.header.well_name)
            continue
        xs.append(x)
        ys.append(y)
        names.append(w.header.well_name)
    return np.array(xs), np.array(ys), names


def _build_well_property_table(
    wells: List[WellLog],
    reservoirs: List[ReservoirSummary],
    prop: str = "avg_porosity",
) -> pd.DataFrame:
    """Return DataFrame with columns [well_name, x, y, value] for a given reservoir property."""
    summary_map = {r.well_name: r for r in reservoirs}
    rows = []
    for w in wells:
        x = w.header.longitude
        y = w.header.latitude
        if x is None or y is None:
            continue
        rs = summary_map.get(w.header.well_name)
        val = getattr(rs, prop, None) if rs else None
        if val is not None:
            rows.append({"well_name": w.header.well_name, "x": x, "y": y, "value": val})
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────
#  Interpolation grid
# ─────────────────────────────────────────────

def interpolate_to_grid(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    nx: int = 100,
    ny: int = 100,
    method: str = "cubic",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Interpolate scattered well data to a regular grid.

    Returns (grid_x, grid_y, grid_z) all shape (ny, nx).
    """
    xi = np.linspace(x.min(), x.max(), nx)
    yi = np.linspace(y.min(), y.max(), ny)
    gx, gy = np.meshgrid(xi, yi)
    gz = griddata((x, y), z, (gx, gy), method=method)
    return gx, gy, gz


# ─────────────────────────────────────────────
#  Map plotting
# ─────────────────────────────────────────────

def _base_map(title: str, figsize=(10, 8)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    return fig, ax


def _add_well_labels(ax, xs, ys, names):
    for x, y, n in zip(xs, ys, names):
        ax.plot(x, y, "k^", ms=8, zorder=5)
        ax.annotate(n, (x, y), textcoords="offset points", xytext=(5, 5), fontsize=7)


def property_map(
    wells: List[WellLog],
    reservoirs: List[ReservoirSummary],
    prop: str          = "avg_porosity",
    cmap: str          = "viridis",
    save_path: Optional[str | Path] = None,
    title: Optional[str] = None,
) -> plt.Figure:
    """
    Interpolated property map coloured by reservoir attribute (φ, Sw, k …).
    """
    df = _build_well_property_table(wells, reservoirs, prop)
    if len(df) < 3:
        logger.warning("Need ≥3 wells with coordinates for interpolation. Got %d.", len(df))
        # Scatter plot only
        fig, ax = _base_map(title or prop.replace("_", " ").title())
        if not df.empty:
            sc = ax.scatter(df["x"], df["y"], c=df["value"], cmap=cmap, s=150, zorder=5)
            plt.colorbar(sc, ax=ax, label=prop)
            for _, row in df.iterrows():
                ax.annotate(row["well_name"], (row["x"], row["y"]),
                            textcoords="offset points", xytext=(5, 5), fontsize=7)
        _save_or_show(fig, save_path)
        return fig

    x, y, z = df["x"].values, df["y"].values, df["value"].values
    gx, gy, gz = interpolate_to_grid(x, y, z)

    fig, ax = _base_map(title or f"{prop.replace('_', ' ').title()} Map")
    im = ax.contourf(gx, gy, gz, levels=15, cmap=cmap, alpha=0.85)
    ax.contour(gx, gy, gz, levels=10, colors="k", linewidths=0.5, alpha=0.5)
    plt.colorbar(im, ax=ax, label=prop.replace("_", " ").title())
    _add_well_labels(ax, x, y, df["well_name"].tolist())

    _save_or_show(fig, save_path)
    return fig


def isopach_map(
    wells: List[WellLog],
    reservoirs: List[ReservoirSummary],
    save_path: Optional[str | Path] = None,
) -> plt.Figure:
    """Net pay thickness map."""
    return property_map(
        wells, reservoirs,
        prop       = "net_pay_m",
        cmap       = "YlOrRd",
        save_path  = save_path,
        title      = "Net Pay Isopach Map",
    )


def structure_map(
    wells: List[WellLog],
    formation_tops: Dict[str, float],   # {well_name: top depth (m TVDss)}
    cmap: str = "terrain_r",
    save_path: Optional[str | Path] = None,
) -> plt.Figure:
    """
    Structure contour map from formation tops (negative = subsurface depth).
    """
    xs, ys, vals = [], [], []
    for w in wells:
        name = w.header.well_name
        if name not in formation_tops:
            continue
        x = w.header.longitude
        y = w.header.latitude
        if x is None or y is None:
            continue
        xs.append(x)
        ys.append(y)
        vals.append(-formation_tops[name])   # negate → deeper = more negative

    if len(xs) < 3:
        logger.warning("Not enough well tops for structure map.")
        return plt.figure()

    xs, ys, vals = np.array(xs), np.array(ys), np.array(vals)
    gx, gy, gz = interpolate_to_grid(xs, ys, vals)

    fig, ax = _base_map("Structure Contour Map (m TVDss)")
    im = ax.contourf(gx, gy, gz, levels=15, cmap=cmap, alpha=0.85)
    cs = ax.contour(gx, gy, gz, levels=10, colors="black", linewidths=0.8)
    ax.clabel(cs, fmt="%d m", fontsize=7)
    plt.colorbar(im, ax=ax, label="Depth (m TVDss)")
    _add_well_labels(ax, xs, ys, list(formation_tops.keys()))

    _save_or_show(fig, save_path)
    return fig


# ─────────────────────────────────────────────
#  Seismic attribute map (amplitude extraction)
# ─────────────────────────────────────────────

def seismic_amplitude_map(
    inline_idx: np.ndarray,
    crossline_idx: np.ndarray,
    amplitude: np.ndarray,
    save_path: Optional[str | Path] = None,
) -> plt.Figure:
    """
    Plot a 2-D seismic attribute map (e.g. RMS amplitude).
    """
    fig, ax = _base_map("Seismic Amplitude Map")
    im = ax.scatter(inline_idx, crossline_idx, c=amplitude, cmap="seismic", s=5, alpha=0.8)
    plt.colorbar(im, ax=ax, label="Amplitude")
    ax.set_xlabel("Inline")
    ax.set_ylabel("Crossline")
    _save_or_show(fig, save_path)
    return fig


# ─────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────

def _save_or_show(fig: plt.Figure, path: Optional[str | Path]):
    if path:
        fig.savefig(str(path), dpi=150, bbox_inches="tight")
        logger.info("Map saved to %s", path)
    plt.close(fig)