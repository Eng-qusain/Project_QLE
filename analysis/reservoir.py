"""
geoai/analysis/reservoir.py
─────────────────────────────
Reservoir characterization from petrophysical results.

Computes
────────
- Net pay / gross intervals
- Average reservoir properties (φ, Sw, k)
- Fluid contacts (OWC, GOC) from Sw profile
- Flow unit classification (FZI / Lorenz coefficient)
- STOIIP / GIIP volumetric estimation
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from project_QLE.core.models import (
    Facies, FluidType, ReservoirSummary, WellLog, ZoneInterval,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Net pay cut-offs
# ─────────────────────────────────────────────

class CutoffSet:
    """Reservoir quality cut-offs (adjustable per basin)."""
    phi_min : float = 0.08       # minimum porosity
    sw_max  : float = 0.60       # maximum water saturation
    vsh_max : float = 0.35       # maximum Vshale
    perm_min: float = 0.1        # minimum permeability (mD)


def apply_cutoffs(df: pd.DataFrame, cutoffs: Optional[CutoffSet] = None) -> pd.Series:
    """Boolean mask: True = reservoir-quality rock."""
    if cutoffs is None:
        cutoffs = CutoffSet()
    mask = pd.Series(True, index=df.index)
    if "PHIE"   in df.columns: mask &= df["PHIE"]    >= cutoffs.phi_min
    if "SW"     in df.columns: mask &= df["SW"]      <= cutoffs.sw_max
    if "VSHALE" in df.columns: mask &= df["VSHALE"]  <= cutoffs.vsh_max
    if "PERM_mD" in df.columns: mask &= df["PERM_mD"] >= cutoffs.perm_min
    return mask


# ─────────────────────────────────────────────
#  Net pay calculator
# ─────────────────────────────────────────────

def compute_net_pay(
    df: pd.DataFrame,
    cutoffs: Optional[CutoffSet] = None,
    depth_col: str = "DEPTH",
) -> float:
    """Return net pay thickness in metres."""
    mask = apply_cutoffs(df, cutoffs)
    if depth_col not in df.columns:
        return 0.0
    depths = df[depth_col].values
    dz = np.abs(np.gradient(depths))
    return float(np.sum(dz[mask.values]))


def compute_net_gross(
    df: pd.DataFrame,
    cutoffs: Optional[CutoffSet] = None,
    depth_col: str = "DEPTH",
) -> dict:
    """
    Compute Gross, Net Pay, and Net/Gross ratio.

    Gross = total stratigraphic thickness of the interval (ft when converted).
    Net   = thickness meeting all reservoir cutoffs.
    N/G   = Net / Gross  (0–1 fraction).

    Returns
    -------
    dict with keys: gross_m, net_m, net_gross, gross_ft, net_ft
    """
    from project_QLE.units import M_TO_FT

    if depth_col not in df.columns:
        return {"gross_m": 0.0, "net_m": 0.0, "net_gross": 0.0,
                "gross_ft": 0.0, "net_ft": 0.0}

    depths = df[depth_col].values
    dz     = np.abs(np.gradient(depths))
    gross  = float(np.sum(dz))

    mask  = apply_cutoffs(df, cutoffs)
    net   = float(np.sum(dz[mask.values]))
    ng    = net / gross if gross > 0 else 0.0

    return {
        "gross_m"   : gross,
        "net_m"     : net,
        "net_gross" : ng,
        "gross_ft"  : gross  * M_TO_FT,
        "net_ft"    : net    * M_TO_FT,
    }


# ─────────────────────────────────────────────
#  Fluid contact detection
# ─────────────────────────────────────────────

def detect_fluid_contact(
    df: pd.DataFrame,
    depth_col: str = "DEPTH",
    sw_col: str    = "SW",
    sw_threshold: float = 0.5,    # above = water zone
    search_top: Optional[float] = None,
    search_base: Optional[float] = None,
) -> Optional[float]:
    """
    Estimate OWC (or GOC) as the depth where Sw crosses sw_threshold.
    Scans downward through the reservoir.
    """
    if sw_col not in df.columns or depth_col not in df.columns:
        return None

    sub = df.copy()
    if search_top  is not None: sub = sub[sub[depth_col] >= search_top]
    if search_base is not None: sub = sub[sub[depth_col] <= search_base]
    sub = sub.sort_values(depth_col)

    sw   = sub[sw_col].values
    dep  = sub[depth_col].values

    for i in range(1, len(sw)):
        if sw[i - 1] < sw_threshold <= sw[i]:
            # Linear interpolation of exact crossing depth
            frac = (sw_threshold - sw[i - 1]) / (sw[i] - sw[i - 1] + 1e-10)
            return float(dep[i - 1] + frac * (dep[i] - dep[i - 1]))

    return None


# ─────────────────────────────────────────────
#  Flow unit classification (FZI)
# ─────────────────────────────────────────────

def flow_zone_indicator(
    phi: np.ndarray,
    k: np.ndarray,
) -> np.ndarray:
    """
    Flow Zone Indicator = sqrt(k/phi) / (phi/(1-phi)) – Amaefule et al. 1993.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        rqi = 0.0314 * np.sqrt(k / phi)       # Reservoir Quality Index
        phi_z = phi / (1 - phi)                # Normalised porosity
        fzi = np.where(phi_z > 0, rqi / phi_z, np.nan)
    return fzi


def lorenz_coefficient(k: np.ndarray, phi: np.ndarray) -> float:
    """
    Lorenz coefficient of heterogeneity (0 = homogeneous, 1 = extreme).
    """
    valid = ~(np.isnan(k) | np.isnan(phi) | (phi <= 0) | (k <= 0))
    kv, pv = k[valid], phi[valid]
    if len(kv) < 2:
        return np.nan

    order  = np.argsort(kv / pv)[::-1]
    kv, pv = kv[order], pv[order]

    cum_kh = np.cumsum(kv * pv) / np.sum(kv * pv)
    cum_ph = np.cumsum(pv)      / np.sum(pv)

    # Area under Lorenz curve vs 45° line
    area = np.trapz(cum_kh, cum_ph)
    return float(2 * area - 1)


# ─────────────────────────────────────────────
#  Volumetrics (STOIIP / GIIP)
# ─────────────────────────────────────────────

def stoiip_bbl(
    area_acres: float,
    net_pay_ft: float,
    phi: float,
    sw: float,
    bo: float = 1.2,     # oil formation volume factor (res bbl / STB)
) -> float:
    """Stock-Tank Oil Initially In Place (STB)."""
    return (7758 * area_acres * net_pay_ft * phi * (1 - sw)) / bo


def giip_mscf(
    area_acres: float,
    net_pay_ft: float,
    phi: float,
    sw: float,
    bg: float = 0.005,   # gas formation volume factor (res ft³ / SCF)
) -> float:
    """Gas Initially In Place (MSCF)."""
    return (43560 * area_acres * net_pay_ft * phi * (1 - sw)) / (bg * 1000)


# ─────────────────────────────────────────────
#  High-level reservoir summary builder
# ─────────────────────────────────────────────

def build_reservoir_summary(
    well: WellLog,
    petro_df: pd.DataFrame,
    zones: List[ZoneInterval],
    cutoffs: Optional[CutoffSet] = None,
    depth_col: str = "DEPTH",
) -> ReservoirSummary:
    """
    Combine petrophysical DataFrame + facies zones into a ReservoirSummary.
    """
    if cutoffs is None:
        cutoffs = CutoffSet()

    reservoir_mask = apply_cutoffs(petro_df, cutoffs)
    res_df = petro_df[reservoir_mask]

    net_pay = compute_net_pay(petro_df, cutoffs, depth_col)

    avg_phi  = float(res_df["PHIE"].mean())    if "PHIE"    in res_df.columns else None
    avg_sw   = float(res_df["SW"].mean())      if "SW"      in res_df.columns else None
    avg_perm = float(res_df["PERM_mD"].mean()) if "PERM_mD" in res_df.columns else None

    owc = detect_fluid_contact(petro_df, depth_col)

    # Annotate zones with average reservoir properties
    enriched_zones: List[ZoneInterval] = []
    for z in zones:
        seg = petro_df[
            (petro_df[depth_col] >= z.top) &
            (petro_df[depth_col] <= z.base)
        ]
        sw_mean  = float(seg["SW"].mean())      if "SW"      in seg.columns else None
        phi_mean = float(seg["PHIE"].mean())    if "PHIE"    in seg.columns else None
        pp_mean  = float(seg["PORE_PRESS_PSI"].mean()) if "PORE_PRESS_PSI" in seg.columns else None
        perm_mean= float(seg["PERM_mD"].mean()) if "PERM_mD" in seg.columns else None

        # Determine fluid type from Sw
        fluid = FluidType.UNKNOWN
        if sw_mean is not None:
            if sw_mean < 0.30:
                fluid = FluidType.OIL
            elif sw_mean < 0.50:
                fluid = FluidType.GAS
            elif sw_mean < 0.70:
                fluid = FluidType.OIL   # oil with edge water
            else:
                fluid = FluidType.WATER

        enriched_zones.append(ZoneInterval(
            top          = z.top,
            base         = z.base,
            facies       = z.facies,
            fluid        = fluid,
            vshale       = None,
            porosity     = phi_mean,
            sw           = sw_mean,
            perm_mD      = perm_mean,
            pressure_psi = pp_mean,
            confidence   = 0.75,   # rule-based default; AI module will update
        ))

    summary = ReservoirSummary(
        well_name     = well.header.well_name,
        zones         = enriched_zones,
        net_pay_m     = net_pay,
        avg_porosity  = avg_phi,
        avg_sw        = avg_sw,
        avg_perm_mD   = avg_perm,
        fluid_contact = owc,
    )
    logger.info(
        "[%s] Reservoir: net_pay=%.1f m, φ=%.2f, Sw=%.2f, OWC=%.1f m",
        well.header.well_name,
        net_pay,
        avg_phi or 0,
        avg_sw or 0,
        owc or -1,
    )
    return summary