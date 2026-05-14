"""
project_QLE/analysis/statistics.py
──────────────────────────────
Statistical analysis for well-log and seismic data.

Includes
────────
- Descriptive stats (mean, std, percentiles, histogram)
- Normality tests (Shapiro-Wilk, K-S)
- Outlier detection (IQR, Z-score, Isolation Forest)
- Trend analysis (linear regression along depth)
- Cross-correlation between log curves
- Moving-window statistics (smoothing, running averages)
- Monte Carlo uncertainty sampling
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import correlate
from sklearn.ensemble import IsolationForest

from project_QLE.core.models import StatisticalResult, WellLog

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Descriptive statistics
# ─────────────────────────────────────────────

def descriptive_stats(
    well: WellLog,
    curve: str,
) -> StatisticalResult:
    """Compute full descriptive statistics for one curve."""
    arr = well.get_curve(curve)
    if arr is None:
        raise KeyError(f"Curve '{curve}' not found in well {well.header.well_name}")

    clean = arr[~np.isnan(arr)]
    if len(clean) == 0:
        raise ValueError(f"Curve '{curve}' is all NaN.")

    hist_counts, hist_edges = np.histogram(clean, bins=50)

    return StatisticalResult(
        curve   = curve,
        well    = well.header.well_name,
        n       = int(len(clean)),
        mean    = float(np.mean(clean)),
        std     = float(np.std(clean)),
        min_val = float(np.min(clean)),
        max_val = float(np.max(clean)),
        p10     = float(np.percentile(clean, 10)),
        p50     = float(np.percentile(clean, 50)),
        p90     = float(np.percentile(clean, 90)),
        skewness= float(stats.skew(clean)),
        kurtosis= float(stats.kurtosis(clean)),
        histogram={
            "edges" : hist_edges.tolist(),
            "counts": hist_counts.tolist(),
        },
    )


def batch_stats(well: WellLog, curves: Optional[List[str]] = None) -> List[StatisticalResult]:
    """Run descriptive_stats on multiple curves at once."""
    targets = curves or list(well.curves.keys())
    results = []
    for c in targets:
        try:
            results.append(descriptive_stats(well, c))
        except (KeyError, ValueError) as e:
            logger.warning("Skipping curve %s: %s", c, e)
    return results


# ─────────────────────────────────────────────
#  Normality tests
# ─────────────────────────────────────────────

def normality_test(arr: np.ndarray, method: str = "shapiro") -> Dict:
    """
    Returns dict with: statistic, p_value, is_normal (p>0.05).
    """
    clean = arr[~np.isnan(arr)]
    if len(clean) < 8:
        return {"statistic": np.nan, "p_value": np.nan, "is_normal": None, "method": method}

    if method == "shapiro":
        # Shapiro-Wilk is limited to ~5000 samples
        sample = clean[:5000]
        stat, p = stats.shapiro(sample)
    elif method == "ks":
        stat, p = stats.kstest(clean, "norm", args=(clean.mean(), clean.std()))
    elif method == "dagostino":
        stat, p = stats.normaltest(clean)
    else:
        raise ValueError(f"Unknown normality test: {method}")

    return {"statistic": float(stat), "p_value": float(p), "is_normal": bool(p > 0.05), "method": method}


# ─────────────────────────────────────────────
#  Outlier detection
# ─────────────────────────────────────────────

def detect_outliers_iqr(arr: np.ndarray, factor: float = 1.5) -> np.ndarray:
    """Boolean mask: True = outlier (beyond IQR fence)."""
    q1 = np.nanpercentile(arr, 25)
    q3 = np.nanpercentile(arr, 75)
    iqr = q3 - q1
    return (arr < q1 - factor * iqr) | (arr > q3 + factor * iqr)


def detect_outliers_zscore(arr: np.ndarray, threshold: float = 3.0) -> np.ndarray:
    mean  = np.nanmean(arr)
    std   = np.nanstd(arr)
    z     = np.abs((arr - mean) / std)
    return z > threshold


def detect_outliers_isolation_forest(
    df: pd.DataFrame,
    features: List[str],
    contamination: float = 0.05,
) -> np.ndarray:
    """Multivariate anomaly detection. Returns boolean mask."""
    X = df[features].values.astype(float)
    nan_rows = np.any(np.isnan(X), axis=1)
    X[nan_rows] = 0  # fill for model (will mark as normal)
    clf = IsolationForest(contamination=contamination, random_state=42, n_jobs=-1)
    preds = clf.fit_predict(X)
    mask = preds == -1
    mask[nan_rows] = False
    return mask


# ─────────────────────────────────────────────
#  Depth trend analysis
# ─────────────────────────────────────────────

def depth_trend(
    depth: np.ndarray,
    curve: np.ndarray,
) -> Dict:
    """Linear regression of log curve vs depth."""
    valid = ~(np.isnan(depth) | np.isnan(curve))
    x, y = depth[valid], curve[valid]
    if len(x) < 2:
        return {}
    slope, intercept, r, p, se = stats.linregress(x, y)
    return {
        "slope"    : float(slope),
        "intercept": float(intercept),
        "r_squared": float(r ** 2),
        "p_value"  : float(p),
        "std_err"  : float(se),
    }


# ─────────────────────────────────────────────
#  Moving-window statistics
# ─────────────────────────────────────────────

def moving_average(arr: np.ndarray, window: int = 11) -> np.ndarray:
    kernel = np.ones(window) / window
    return np.convolve(arr, kernel, mode="same")


def moving_std(arr: np.ndarray, window: int = 11) -> np.ndarray:
    series = pd.Series(arr)
    return series.rolling(window, center=True, min_periods=1).std().values


# ─────────────────────────────────────────────
#  Log-to-log cross-correlation
# ─────────────────────────────────────────────

def cross_correlate_curves(
    a: np.ndarray,
    b: np.ndarray,
    max_lag: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Cross-correlate two log arrays (e.g. GR from two wells after depth shift).

    Returns
    -------
    lags         : array of integer lag indices
    correlation  : normalised correlation values
    """
    a_clean = np.where(np.isnan(a), 0, a)
    b_clean = np.where(np.isnan(b), 0, b)
    # Normalise
    a_n = (a_clean - a_clean.mean()) / (a_clean.std() + 1e-10)
    b_n = (b_clean - b_clean.mean()) / (b_clean.std() + 1e-10)
    full = correlate(a_n, b_n, mode="full") / len(a_n)
    mid  = len(full) // 2
    lags = np.arange(-max_lag, max_lag + 1)
    corr = full[mid - max_lag : mid + max_lag + 1]
    return lags, corr


def pearson_matrix(df: pd.DataFrame, curves: Optional[List[str]] = None) -> pd.DataFrame:
    """Pearson correlation matrix for selected curves."""
    cols = curves or [c for c in df.columns if df[c].dtype in (float, int, "float64", "int64")]
    return df[cols].corr(method="pearson")


# ─────────────────────────────────────────────
#  Monte Carlo uncertainty
# ─────────────────────────────────────────────

def monte_carlo_porosity(
    phi_mean: float,
    phi_std: float,
    n_samples: int = 10_000,
) -> Dict:
    """
    Simple MC sampling of porosity uncertainty.
    Returns P10/P50/P90 and histogram.
    """
    samples = np.random.normal(phi_mean, phi_std, n_samples)
    samples = np.clip(samples, 0, 1)
    counts, edges = np.histogram(samples, bins=50)
    return {
        "p10": float(np.percentile(samples, 10)),
        "p50": float(np.percentile(samples, 50)),
        "p90": float(np.percentile(samples, 90)),
        "mean": float(samples.mean()),
        "std" : float(samples.std()),
        "histogram": {"edges": edges.tolist(), "counts": counts.tolist()},
    }