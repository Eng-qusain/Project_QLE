"""
project_QLE/units.py
─────────────────────
Unit conversion for US Field Units display.

Project_QLE stores all data internally in SI/metric units.
This module converts to US field units for display.

Authors: Eng. Qusai Alnuaimat · Dr. Lutfi Dugdug
         Waha Oil Company – Exploration Department
"""
from __future__ import annotations
import numpy as np

# ── Conversion factors ───────────────────────────────────────
M_TO_FT   = 3.28084          # metres → feet
FT_TO_M   = 1.0 / M_TO_FT   # feet → metres
BAR_TO_PSI = 14.5038
KPA_TO_PSI = 0.145038
G_CC_TO_LB_GAL = 8.33        # g/cc → lb/gal (mud weight)

# Volume
M3_TO_BBL  = 6.28981
BBL_TO_M3  = 1.0 / M3_TO_BBL

# Temperature
def c_to_f(c): return c * 9.0 / 5.0 + 32.0
def f_to_c(f): return (f - 32.0) * 5.0 / 9.0


# ── Depth ────────────────────────────────────────────────────
def m_to_ft(val):
    """Convert metres → feet (scalar or numpy array)."""
    if val is None:
        return None
    return val * M_TO_FT

def ft_to_m(val):
    """Convert feet → metres."""
    if val is None:
        return None
    return val * FT_TO_M


# ── Pressure ─────────────────────────────────────────────────
def psi_label() -> str:    return "psi"
def depth_label() -> str:  return "ft"


# ── Display formatters ───────────────────────────────────────
def fmt_depth(m: float) -> str:
    """Format a depth value in ft."""
    if m is None:
        return "N/A"
    return f"{m_to_ft(m):.0f} ft"

def fmt_depth_range(top_m: float, base_m: float) -> str:
    return f"{m_to_ft(top_m):.0f}–{m_to_ft(base_m):.0f} ft"

def fmt_thickness(m: float) -> str:
    if m is None:
        return "N/A"
    return f"{m_to_ft(m):.1f} ft"

def fmt_perm(md: float) -> str:
    if md is None:
        return "N/A"
    return f"{md:.1f} mD"

def fmt_pressure(psi: float) -> str:
    if psi is None:
        return "N/A"
    return f"{psi:.0f} psi"

def fmt_gradient(psi_per_ft: float) -> str:
    return f"{psi_per_ft:.3f} psi/ft"

def fmt_phi(fraction: float) -> str:
    if fraction is None:
        return "N/A"
    return f"{fraction:.1%}"

def fmt_sw(fraction: float) -> str:
    return fmt_phi(fraction)


# ── DataFrame depth conversion ───────────────────────────────
def convert_depth_col_to_ft(df, depth_col: str = "DEPTH"):
    """Return a copy of df with the depth column converted to feet."""
    import pandas as pd
    df = df.copy()
    if depth_col in df.columns:
        df[depth_col] = df[depth_col] * M_TO_FT
    return df


# ── STOIIP/GIIP already in bbl/MSCF from reservoir.py ───────
# No conversion needed for volumetrics.

# ── Net pay / gross in feet ──────────────────────────────────
def net_pay_ft(net_pay_m: float) -> float:
    return m_to_ft(net_pay_m) if net_pay_m is not None else None

# ── Gradient psi/ft → g/cc ──────────────────────────────────
def psi_ft_to_gcc(grad_psi_ft: float) -> float:
    """Convert psi/ft gradient to equivalent mud weight in g/cc."""
    return grad_psi_ft / 0.4335

def gcc_to_psi_ft(gcc: float) -> float:
    return gcc * 0.4335


# ── Unit label helpers ───────────────────────────────────────
UNIT_LABELS = {
    "DEPTH":           "ft",
    "GR":              "GAPI",
    "RHOB":            "g/cc",
    "NPHI":            "v/v",
    "RT":              "Ω·m",
    "DT":              "µs/ft",
    "VSHALE":          "v/v",
    "PHIE":            "v/v",
    "PHID":            "v/v",
    "PHIND":           "v/v",
    "SW":              "v/v",
    "SH":              "v/v",
    "PERM_mD":         "mD",
    "PORE_PRESS_PSI":  "psi",
    "FACIES":          "—",
}

def unit_label(mnemonic: str) -> str:
    return UNIT_LABELS.get(mnemonic.upper(), "")