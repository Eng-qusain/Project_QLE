"""
project_QLE/analysis/petro_summaries.py
────────────────────────────────────────
Generate petrophysical summaries and textual descriptions.

Covers: porosity, permeability, saturation summaries,
        formation top descriptions, DST interpretation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


# ── Summary dataclasses ──────────────────────────────────────

@dataclass
class PorositySummary:
    mean: float
    std: float
    min_val: float
    max_val: float
    p10: float
    p50: float
    p90: float
    quality: str        # 'Poor' | 'Fair' | 'Good' | 'Excellent'
    net_pay_m: float = 0.0


@dataclass
class PermeabilitySummary:
    mean_md: float
    std_md: float
    min_md: float
    max_md: float
    p10_md: float
    p50_md: float
    p90_md: float
    quality: str        # 'Poor' | 'Fair' | 'Good' | 'Excellent'
    log_mean_md: float = 0.0   # geometric mean (log-space average)


@dataclass
class SaturationSummary:
    sw_mean: float
    sw_std: float
    sh_mean: float      # total hydrocarbon saturation
    so_mean: float      # oil saturation (estimated)
    sg_mean: float      # gas saturation (estimated)
    fluid_type: str     # 'Oil' | 'Gas' | 'Water' | 'Mixed'


@dataclass
class PetroSummaryBundle:
    """All three summaries together, plus formatted text."""
    well_name: str
    basin: str
    porosity: Optional[PorositySummary]
    permeability: Optional[PermeabilitySummary]
    saturation: Optional[SaturationSummary]
    description: str = ""   # auto-generated narrative


# ── Calculation functions ────────────────────────────────────

def _quality_label(value: float, thresholds: tuple) -> str:
    """(poor_max, fair_max, good_max) → quality string."""
    poor_max, fair_max, good_max = thresholds
    if value <= poor_max:
        return "Poor"
    if value <= fair_max:
        return "Fair"
    if value <= good_max:
        return "Good"
    return "Excellent"


def summarise_porosity(df: pd.DataFrame,
                        phi_col: str = "PHIE",
                        depth_col: str = "DEPTH",
                        cutoff: float = 0.08) -> Optional[PorositySummary]:
    """Compute porosity statistics from a petrophysics DataFrame."""
    if phi_col not in df.columns:
        return None
    phi = df[phi_col].dropna()
    if len(phi) < 3:
        return None

    mean   = float(phi.mean())
    std    = float(phi.std())
    min_v  = float(phi.min())
    max_v  = float(phi.max())
    p10    = float(phi.quantile(0.10))
    p50    = float(phi.quantile(0.50))
    p90    = float(phi.quantile(0.90))
    qual   = _quality_label(mean, (0.05, 0.10, 0.18))

    # Net pay: sum of intervals above cutoff
    net = 0.0
    if depth_col in df.columns and len(df[depth_col].dropna()) > 1:
        above = df[df[phi_col] >= cutoff]
        if len(above) > 1:
            depths = df[depth_col].dropna().values
            step = float(np.median(np.diff(np.sort(depths))))
            net = float(len(above) * step)

    return PorositySummary(mean=mean, std=std, min_val=min_v, max_val=max_v,
                            p10=p10, p50=p50, p90=p90, quality=qual, net_pay_m=net)


def summarise_permeability(df: pd.DataFrame,
                            k_col: str = "PERM_mD") -> Optional[PermeabilitySummary]:
    """Compute permeability statistics."""
    if k_col not in df.columns:
        return None
    k = df[k_col].dropna()
    k = k[k > 0]   # permeability must be positive
    if len(k) < 3:
        return None

    mean_md   = float(k.mean())
    std_md    = float(k.std())
    min_md    = float(k.min())
    max_md    = float(k.max())
    p10_md    = float(k.quantile(0.10))
    p50_md    = float(k.quantile(0.50))
    p90_md    = float(k.quantile(0.90))
    log_mean  = float(np.exp(np.log(k).mean()))   # geometric mean
    qual      = _quality_label(mean_md, (1.0, 10.0, 100.0))

    return PermeabilitySummary(mean_md=mean_md, std_md=std_md, min_md=min_md,
                                max_md=max_md, p10_md=p10_md, p50_md=p50_md,
                                p90_md=p90_md, quality=qual, log_mean_md=log_mean)


def summarise_saturation(df: pd.DataFrame,
                          sw_col: str = "SW") -> Optional[SaturationSummary]:
    """Compute saturation statistics and infer fluid type."""
    if sw_col not in df.columns:
        return None
    sw = df[sw_col].dropna()
    if len(sw) < 3:
        return None

    sw_mean = float(sw.mean())
    sw_std  = float(sw.std())
    sh_mean = 1.0 - sw_mean

    # Simplified: if Sh > 0.5 and SH looks oily vs gassy
    # (real gas detection needs NPHI/RHOB crossover)
    if sw_mean > 0.70:
        fluid   = "Water"
        so_mean = sh_mean * 0.1
        sg_mean = sh_mean * 0.9
    elif sh_mean > 0.5:
        fluid   = "Oil"
        so_mean = sh_mean * 0.85
        sg_mean = sh_mean * 0.15
    elif sh_mean > 0.25:
        fluid   = "Mixed"
        so_mean = sh_mean * 0.5
        sg_mean = sh_mean * 0.5
    else:
        fluid   = "Water"
        so_mean = sh_mean * 0.2
        sg_mean = sh_mean * 0.8

    return SaturationSummary(sw_mean=sw_mean, sw_std=sw_std, sh_mean=sh_mean,
                              so_mean=so_mean, sg_mean=sg_mean, fluid_type=fluid)


def build_bundle(well_name: str, basin: str,
                 df: pd.DataFrame) -> PetroSummaryBundle:
    """Build a full summary bundle from a petrophysics DataFrame."""
    phi_s = summarise_porosity(df)
    k_s   = summarise_permeability(df)
    sat_s = summarise_saturation(df)
    desc  = _generate_description(well_name, basin, phi_s, k_s, sat_s)
    return PetroSummaryBundle(
        well_name=well_name, basin=basin,
        porosity=phi_s, permeability=k_s, saturation=sat_s,
        description=desc,
    )


def _generate_description(well_name: str, basin: str,
                           phi: Optional[PorositySummary],
                           k: Optional[PermeabilitySummary],
                           sat: Optional[SaturationSummary]) -> str:
    """Auto-generate a professional summary paragraph."""
    parts = [f"Well {well_name} ({basin} Basin) — Petrophysical Summary\n"]

    if phi:
        parts.append(
            f"POROSITY: {phi.quality} quality reservoir. Average effective porosity "
            f"{phi.mean:.1%} (P10={phi.p10:.1%} / P50={phi.p50:.1%} / P90={phi.p90:.1%}). "
            f"Range {phi.min_val:.1%}–{phi.max_val:.1%}. "
            + (f"Estimated net pay: {phi.net_pay_m:.1f} m." if phi.net_pay_m > 0 else "")
        )

    if k:
        parts.append(
            f"PERMEABILITY: {k.quality} quality. Mean {k.mean_md:.1f} mD "
            f"(geometric mean {k.log_mean_md:.1f} mD). "
            f"P50 = {k.p50_md:.1f} mD. Range {k.min_md:.1f}–{k.max_md:.1f} mD."
        )

    if sat:
        parts.append(
            f"SATURATION: Dominant fluid is {sat.fluid_type}. "
            f"Average Sw = {sat.sw_mean:.1%} (Sh = {sat.sh_mean:.1%}). "
            f"Estimated So = {sat.so_mean:.1%}, Sg = {sat.sg_mean:.1%}."
        )

    return "\n\n".join(parts)


# ── Formation top description ────────────────────────────────

LITHO_DESCRIPTIONS = {
    "Sandstone" : (
        "Clastic reservoir. Typically high primary porosity with intergranular pore space. "
        "Permeability controlled by grain size and sorting. Reservoir quality degrades with "
        "clay content and cementation."
    ),
    "Shale" : (
        "Fine-grained clastic. Non-reservoir (seal or barrier). Very low permeability (<0.01 mD). "
        "May act as source rock or regional seal above reservoir."
    ),
    "Limestone" : (
        "Carbonate reservoir. Porosity dominated by interparticle, vuggy, or moldic pore types. "
        "Subject to diagenetic modification — dissolution enhances porosity; cementation reduces it. "
        "Fractures can significantly improve permeability."
    ),
    "Dolomite" : (
        "Diagenetically altered carbonate. Often better reservoir quality than precursor limestone "
        "due to volume reduction during dolomitisation. Intercrystalline and vuggy porosity common."
    ),
    "Anhydrite" : (
        "Evaporite. Non-reservoir. Common seal in Sirte Basin above carbonate reservoirs. "
        "Brittle; fractures if present may locally increase permeability."
    ),
    "Unknown" : "Lithology undetermined from available data.",
}


def describe_formation(formation_name: str, lithology: str,
                        top_m: float, base_m: float,
                        avg_phi: Optional[float] = None,
                        avg_k: Optional[float] = None) -> str:
    """Generate a description for a formation top/interval."""
    thickness = base_m - top_m if base_m > top_m else 0.0
    litho_txt = LITHO_DESCRIPTIONS.get(lithology, LITHO_DESCRIPTIONS["Unknown"])

    lines = [
        f"Formation: {formation_name}",
        f"Lithology : {lithology}",
        f"Interval  : {top_m:.1f} – {base_m:.1f} m  (thickness {thickness:.1f} m)",
        "",
        litho_txt,
    ]
    if avg_phi is not None:
        lines.append(f"\nMeasured Avg φ = {avg_phi:.1%}")
    if avg_k is not None:
        lines.append(f"Measured Avg k = {avg_k:.1f} mD")

    return "\n".join(lines)


# ── DST interpretation ───────────────────────────────────────

def interpret_dst(test: Dict) -> str:
    """Generate a readable DST test interpretation."""
    name     = test.get("test_name", "DST")
    depth    = test.get("depth_m", 0)
    fluid    = test.get("fluid_type", "Unknown")
    isip     = test.get("initial_shut_in_psi")
    fsip     = test.get("final_shut_in_psi")
    rate_bpd = test.get("flow_rate_bpd")
    k_md     = test.get("permeability_md")
    rp_psi   = test.get("reservoir_pressure_psi")
    skin     = test.get("skin_factor")
    gor      = test.get("gor_scfbbl")
    api      = test.get("api_gravity")

    lines = [
        f"╔══ DST: {name} ══",
        f"  Depth        : {depth:.1f} m",
        f"  Fluid type   : {fluid}",
    ]
    if isip and fsip:
        lines.append(f"  Shut-in P    : {isip:.0f} → {fsip:.0f} psi")
    if rate_bpd:
        lines.append(f"  Flow rate    : {rate_bpd:.1f} bpd")
    if k_md:
        lines.append(f"  Permeability : {k_md:.1f} mD")
    if rp_psi:
        lines.append(f"  Reservoir P  : {rp_psi:.0f} psi")
    if skin is not None:
        cond = "damaged" if skin > 5 else "stimulated" if skin < -2 else "undamaged"
        lines.append(f"  Skin factor  : {skin:.1f}  ({cond})")
    if gor:
        lines.append(f"  GOR          : {gor:.0f} scf/bbl")
    if api:
        lines.append(f"  API gravity  : {api:.1f}°")

    lines.append("╚" + "═" * 35)
    return "\n".join(lines)