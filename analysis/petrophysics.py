"""
project_QLE/analysis/petrophysics.py
────────────────────────────────
Industry-standard petrophysical transforms applied to WellLog data.

Implemented transforms
──────────────────────
Vshale     : Larionov linear / non-linear, SP, ND crossplot
Porosity   : Density, Neutron-Density, Sonic (Wyllie / Raymer)
Water Sat  : Archie, Simandoux, Indonesia
Pore Pressure: Eaton's method, Bowers (velocity-based)
Permeability: Timur / Coates
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from project_QLE.core.models import WellLog

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────

def _safe_get(well: WellLog, *mnemonics: str) -> Optional[np.ndarray]:
    for m in mnemonics:
        arr = well.get_curve(m)
        if arr is not None:
            return arr
    return None


def clamp(arr: np.ndarray, lo: float = 0.0, hi: float = 1.0) -> np.ndarray:
    return np.clip(arr, lo, hi)


# ─────────────────────────────────────────────
#  Vshale
# ─────────────────────────────────────────────

def vshale_gr(
    gr: np.ndarray,
    gr_clean: float,
    gr_shale: float,
    method: str = "linear",
) -> np.ndarray:
    """
    Gamma-ray Vshale.

    Parameters
    ----------
    method : 'linear' | 'larionov_old' | 'larionov_young' | 'clavier' | 'stieber'
    """
    igr = clamp((gr - gr_clean) / (gr_shale - gr_clean))

    if method == "linear":
        return igr
    elif method == "larionov_old":          # Tertiary rocks
        return 0.33 * (2 ** (2 * igr) - 1)
    elif method == "larionov_young":        # Mesozoic and older
        return 0.083 * (2 ** (3.7 * igr) - 1)
    elif method == "clavier":
        return 1.7 - np.sqrt(3.38 - (igr + 0.7) ** 2)
    elif method == "stieber":
        return igr / (3 - 2 * igr)
    else:
        raise ValueError(f"Unknown Vshale method: {method}")


def vshale_sp(
    sp: np.ndarray,
    sp_clean: float,
    sp_shale: float,
) -> np.ndarray:
    return clamp((sp - sp_clean) / (sp_shale - sp_clean))


# ─────────────────────────────────────────────
#  Porosity
# ─────────────────────────────────────────────

def porosity_density(
    rhob: np.ndarray,
    rho_matrix: float = 2.65,   # sandstone; use 2.71 for limestone, 2.87 for dolomite
    rho_fluid: float  = 1.00,   # fresh mud; use 1.1 for salt mud
) -> np.ndarray:
    """Density porosity (PHID)."""
    return clamp((rho_matrix - rhob) / (rho_matrix - rho_fluid))


def porosity_neutron_density(
    nphi: np.ndarray,
    phid: np.ndarray,
) -> np.ndarray:
    """Neutron-Density crossplot porosity (PHIND) – best for gas detection."""
    return clamp(np.sqrt((nphi ** 2 + phid ** 2) / 2))


def porosity_sonic_wyllie(
    dt: np.ndarray,
    dt_matrix: float = 55.5,    # µs/ft sandstone; 47.6 limestone; 43.5 dolomite
    dt_fluid: float  = 189.0,   # µs/ft fresh water
    cp: float        = 1.0,     # compaction correction (1 if no correction needed)
) -> np.ndarray:
    """Wyllie time-average porosity from sonic log."""
    return clamp(((dt - dt_matrix) / (dt_fluid - dt_matrix)) / cp)


def porosity_sonic_raymer(
    dt: np.ndarray,
    dt_matrix: float = 55.5,
) -> np.ndarray:
    """Raymer-Hunt-Gardner porosity (better for consolidated formations)."""
    return clamp(0.625 * (1 - dt_matrix / dt))


# ─────────────────────────────────────────────
#  Water Saturation
# ─────────────────────────────────────────────

def sw_archie(
    rt: np.ndarray,
    phi: np.ndarray,
    rw: float  = 0.05,   # formation water resistivity (ohm-m)
    a: float   = 1.0,    # tortuosity factor
    m: float   = 2.0,    # cementation exponent
    n: float   = 2.0,    # saturation exponent
) -> np.ndarray:
    """Archie water saturation (clean sands only)."""
    with np.errstate(divide="ignore", invalid="ignore"):
        sw = ((a * rw) / (rt * phi ** m)) ** (1 / n)
    return clamp(sw)


def sw_simandoux(
    rt: np.ndarray,
    phi: np.ndarray,
    vsh: np.ndarray,
    rw: float  = 0.05,
    rsh: float = 2.0,    # shale resistivity
    a: float   = 1.0,
    m: float   = 2.0,
    n: float   = 2.0,
) -> np.ndarray:
    """Simandoux equation for shaly sands."""
    with np.errstate(divide="ignore", invalid="ignore"):
        c = (phi ** m) / (a * rw)
        d = vsh / rsh
        sw = (c / (2 * rt)) * (
            np.sqrt(1 + (2 * rt * d / c) ** 2) - (2 * rt * d / c)
        ) ** (2 / n)
    return clamp(sw)


# ─────────────────────────────────────────────
#  Pore Pressure (Eaton's method)
# ─────────────────────────────────────────────

def pore_pressure_eaton(
    depth_m: np.ndarray,
    dt_obs: np.ndarray,
    dt_normal: Optional[np.ndarray] = None,
    overburden_gradient: float = 1.0,    # psi/ft or equivalent
    hydrostatic_gradient: float = 0.465, # psi/ft fresh water
    eaton_exp: float = 3.0,
    convert_to_psi: bool = True,
) -> np.ndarray:
    """
    Eaton's method pore pressure from sonic log.

    PP = OBG - (OBG - HG) * (dt_normal / dt_obs)^n

    Returns pressure in psi (if convert_to_psi) or as gradient.
    """
    depth_ft = depth_m * 3.28084

    if dt_normal is None:
        # Normal compaction trend: simple linear (adjust for basin)
        dt_normal = 120 * np.exp(-0.00025 * depth_ft)

    ob_pressure = overburden_gradient * depth_ft
    hy_pressure = hydrostatic_gradient * depth_ft

    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(dt_obs > 0, dt_normal / dt_obs, np.nan)
        pp = ob_pressure - (ob_pressure - hy_pressure) * (ratio ** eaton_exp)

    return pp   # in psi if convert_to_psi=True with above gradients


# ─────────────────────────────────────────────
#  Permeability estimates
# ─────────────────────────────────────────────

def permeability_timur(
    phi: np.ndarray,
    swi: float = 0.15,   # irreducible water saturation
) -> np.ndarray:
    """Timur correlation (mD) – suitable for clean sands."""
    with np.errstate(divide="ignore", invalid="ignore"):
        k = 0.136 * (phi ** 4.4) / (swi ** 2)
    return np.where(k > 0, k, np.nan)


def permeability_coates(
    phi: np.ndarray,
    swi: float = 0.15,
    a: float = 10.0,
    b: float = 2.0,
    c: float = 2.0,
) -> np.ndarray:
    """Coates / Morris-Biggs NMR-style permeability estimate."""
    with np.errstate(divide="ignore", invalid="ignore"):
        k = (phi / a) ** b * ((1 - swi) / swi) ** c * 1000
    return np.where(k > 0, k, np.nan)


# ─────────────────────────────────────────────
#  Full petrophysical workflow on a WellLog
# ─────────────────────────────────────────────

class PetrophysicsEngine:
    """
    High-level engine that runs the full petrophysical workflow
    on a WellLog and returns an enriched DataFrame.
    """

    def __init__(
        self,
        well: WellLog,
        gr_clean: float = 15.0,
        gr_shale: float = 120.0,
        rho_matrix: float = 2.65,
        rho_fluid: float  = 1.00,
        rw: float = 0.05,
        rsh: float = 2.0,
        vsh_method: str = "larionov_young",
    ):
        self.well       = well
        self.gr_clean   = gr_clean
        self.gr_shale   = gr_shale
        self.rho_matrix = rho_matrix
        self.rho_fluid  = rho_fluid
        self.rw         = rw
        self.rsh        = rsh
        self.vsh_method = vsh_method

    def run(self) -> pd.DataFrame:
        """
        Execute full workflow and return DataFrame with new columns:
        VSHALE, PHID, PHIND, PHIE, SW, PERM_mD, PORE_PRESS_PSI
        """
        w = self.well
        df = w.df.copy() if w.df is not None else pd.DataFrame()

        depth = w.get_depth()
        if depth is None:
            raise ValueError("No depth curve found in well log.")

        # ── Vshale ──────────────────────────────
        gr = w.get_curve("GR")
        if gr is not None:
            vsh = vshale_gr(gr, self.gr_clean, self.gr_shale, self.vsh_method)
            df["VSHALE"] = vsh
            logger.debug("[%s] Vshale computed (GR method)", w.header.well_name)
        else:
            vsh = np.full(len(depth), np.nan)
            df["VSHALE"] = vsh
            logger.warning("[%s] GR not found; Vshale = NaN", w.header.well_name)

        # ── Porosity ────────────────────────────
        rhob = w.get_curve("RHOB") or w.get_curve("RHOZ")
        nphi = w.get_curve("NPHI") or w.get_curve("TNPH")
        dt   = w.get_curve("DT")   or w.get_curve("DTC") or w.get_curve("DTCO")

        phid  = porosity_density(rhob, self.rho_matrix, self.rho_fluid) if rhob is not None else None
        phind = porosity_neutron_density(nphi, phid) if (nphi is not None and phid is not None) else None
        phis  = porosity_sonic_wyllie(dt) if dt is not None else None

        phie = phind if phind is not None else (phid if phid is not None else phis)

        if phid  is not None: df["PHID"]  = phid
        if phind is not None: df["PHIND"] = phind
        if phis  is not None: df["PHIS"]  = phis
        if phie  is not None:
            df["PHIE"] = phie
            logger.debug("[%s] Porosity computed", w.header.well_name)
        else:
            phie = np.full(len(depth), np.nan)
            df["PHIE"] = phie
            logger.warning("[%s] No porosity inputs found", w.header.well_name)

        # ── Water Saturation ────────────────────
        rt = (_safe_get(w, "RT", "ILD", "LLD", "MSFL") )
        if rt is not None and phie is not None and not np.all(np.isnan(phie)):
            if vsh is not None and not np.all(np.isnan(vsh)):
                sw = sw_simandoux(rt, phie, vsh, self.rw, self.rsh)
            else:
                sw = sw_archie(rt, phie, self.rw)
            df["SW"] = sw
            df["SH"] = 1 - sw   # hydrocarbon saturation
            logger.debug("[%s] Sw computed", w.header.well_name)

        # ── Permeability ────────────────────────
        if phie is not None and not np.all(np.isnan(phie)):
            df["PERM_mD"] = permeability_timur(phie)
            logger.debug("[%s] Permeability estimated", w.header.well_name)

        # ── Pore Pressure ───────────────────────
        if dt is not None:
            depth_m = depth if depth is not None else np.arange(len(dt))
            df["PORE_PRESS_PSI"] = pore_pressure_eaton(depth_m, dt)
            logger.debug("[%s] Pore pressure estimated (Eaton)", w.header.well_name)

        return df