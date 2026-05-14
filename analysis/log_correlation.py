"""Well log correlation helpers for Project_QLE."""

from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from Project_QLE.core.models import CorrelationResult, WellLog


def _depth_column(df: pd.DataFrame) -> str:
    for key in ("DEPTH", "DEPT", "MD", "TVD"):
        if key in df.columns:
            return key
    return df.columns[0]


def _ensure_df(well: WellLog) -> pd.DataFrame:
    if well.df is not None:
        df = well.df.copy()
    else:
        depth = well.get_depth()
        if depth is None:
            raise ValueError("Well has no depth information")
        data = {"DEPTH": depth}
        for name, curve in well.curves.items():
            data[name.upper()] = curve.array
        df = pd.DataFrame(data)

    df = df.rename(columns={c: c.upper() for c in df.columns})
    depth_col = _depth_column(df)
    return df.sort_values(by=depth_col).reset_index(drop=True)


def resample_to_common_depth(
    well_a: WellLog,
    well_b: WellLog,
    curve: str,
    step: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    df_a = _ensure_df(well_a)
    df_b = _ensure_df(well_b)

    depth_a = _depth_column(df_a)
    depth_b = _depth_column(df_b)
    if curve not in df_a.columns:
        raise ValueError(f"Curve '{curve}' not found in well {well_a.header.well_name}")
    if curve not in df_b.columns:
        raise ValueError(f"Curve '{curve}' not found in well {well_b.header.well_name}")

    da = df_a[depth_a].to_numpy(dtype=float)
    db = df_b[depth_b].to_numpy(dtype=float)
    if step is None:
        step = float(np.nanmedian(np.diff(np.unique(np.concatenate([da, db])))))
        if not np.isfinite(step) or step <= 0:
            step = 0.5

    start = max(np.nanmin(da), np.nanmin(db))
    stop = min(np.nanmax(da), np.nanmax(db))
    if stop <= start:
        raise ValueError("Wells do not overlap in depth")

    grid = np.arange(start, stop + step / 2, step)

    def _interp(series: pd.Series, depths: np.ndarray) -> np.ndarray:
        valid = series.notna() & np.isfinite(depths)
        if valid.sum() < 2:
            return np.full(grid.shape, np.nan, dtype=float)
        return np.interp(grid, depths[valid], series.to_numpy(dtype=float)[valid])

    a_vals = _interp(df_a[curve], da)
    b_vals = _interp(df_b[curve], db)
    return grid, a_vals, b_vals, step


def correlate_wells(
    well_a: WellLog,
    well_b: WellLog,
    curve: str = "GR",
    step: Optional[float] = None,
) -> CorrelationResult:
    depth, a_vals, b_vals, actual_step = resample_to_common_depth(well_a, well_b, curve, step=step)
    mask = np.isfinite(a_vals) & np.isfinite(b_vals)
    if mask.sum() < 2:
        raise ValueError("Not enough data overlap for correlation")

    a_clean = a_vals[mask]
    b_clean = b_vals[mask]
    pearson_r = float(np.corrcoef(a_clean, b_clean)[0, 1])

    norm_a = a_clean - a_clean.mean()
    norm_b = b_clean - b_clean.mean()
    xcorr = np.correlate(norm_a, norm_b, mode="full")
    lag_idx = int(np.nanargmax(xcorr))
    lag_m = float((lag_idx - (len(norm_a) - 1)) * actual_step)

    return CorrelationResult(
        well_a=well_a.header.well_name,
        well_b=well_b.header.well_name,
        curve=curve,
        pearson_r=pearson_r,
        lag_m=lag_m,
        matched_zones=[],
    )


def correlate_well_suite(
    wells: Iterable[WellLog],
    curves: List[str] = ["GR"],
    step: Optional[float] = None,
) -> List[CorrelationResult]:
    wells = list(wells)
    results: List[CorrelationResult] = []
    for i in range(len(wells)):
        for j in range(i + 1, len(wells)):
            for curve in curves:
                try:
                    results.append(correlate_wells(wells[i], wells[j], curve, step=step))
                except Exception:
                    continue
    return results


def pick_formation_tops(
    well: WellLog,
    curve: str = "GR",
    n_tops: int = 3,
) -> List[float]:
    df = _ensure_df(well)
    depth_col = _depth_column(df)
    if curve not in df.columns:
        return []

    series = df[curve].to_numpy(dtype=float)
    depths = df[depth_col].to_numpy(dtype=float)
    valid = np.isfinite(series) & np.isfinite(depths)
    if valid.sum() == 0:
        return []

    indices = np.argsort(series[valid])[-n_tops:][::-1]
    tops = sorted(depths[valid][indices])
    return tops


def correlate_markers_across_wells(
    wells: Iterable[WellLog],
    curve: str = "GR",
    n_tops: int = 3,
) -> pd.DataFrame:
    records: List[dict] = []
    for well in wells:
        tops = pick_formation_tops(well, curve, n_tops=n_tops)
        for rank, depth in enumerate(tops, start=1):
            records.append({
                "Well": well.header.well_name,
                "Curve": curve,
                "Top #": rank,
                "Depth_m": float(depth),
            })
    return pd.DataFrame(records)
