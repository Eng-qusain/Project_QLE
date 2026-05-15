"""
project_QLE/core/libya_geology.py
───────────────────────────────────
Libyan basin defaults and field metadata for Project_QLE.
 
All four petroleum basins calibrated with the FULL parameter set
required by PetrophysicsEngine. Do not remove any keys.
"""
from __future__ import annotations
from typing import Dict, List
 
# ── Basin display names ──────────────────────────────────────
LIBYAN_BASINS: Dict[str, str] = {
    "SIRTE"    : "Sirte Basin",
    "GHADAMES" : "Ghadames Basin",
    "MURZUQ"   : "Murzuq Basin",
    "OFFSHORE" : "Libyan Offshore (Mediterranean)",
    "KUFRA"    : "Al Kufra Basin",
    "CYRENAICA": "Cyrenaica Platform",
}
 
# ── Known Libyan fields (for map display) ────────────────────
LIBYAN_FIELDS: List[Dict] = [
    {"name": "Sarir",              "basin": "SIRTE",    "fluid": "Oil", "api": 38, "lat": 28.00, "lon": 21.80},
    {"name": "Messla",             "basin": "SIRTE",    "fluid": "Oil", "api": 36, "lat": 28.45, "lon": 20.80},
    {"name": "Nafoora-Augila",     "basin": "SIRTE",    "fluid": "Oil", "api": 40, "lat": 29.10, "lon": 21.60},
    {"name": "Intisar D",          "basin": "SIRTE",    "fluid": "Oil", "api": 44, "lat": 29.20, "lon": 21.00},
    {"name": "Amal",               "basin": "SIRTE",    "fluid": "Oil", "api": 43, "lat": 28.80, "lon": 22.30},
    {"name": "Nasser (Zelten)",    "basin": "SIRTE",    "fluid": "Oil", "api": 41, "lat": 29.50, "lon": 19.50},
    {"name": "Waha",               "basin": "SIRTE",    "fluid": "Oil", "api": 32, "lat": 29.72, "lon": 20.17},
    {"name": "El Sharara",         "basin": "MURZUQ",   "fluid": "Oil", "api": 41, "lat": 27.80, "lon": 13.20},
    {"name": "El Feel (Elephant)", "basin": "MURZUQ",   "fluid": "Oil", "api": 40, "lat": 27.30, "lon": 14.10},
    {"name": "Wafa Gas",           "basin": "GHADAMES", "fluid": "Gas", "api": 55, "lat": 27.90, "lon": 10.70},
    {"name": "Gialo",              "basin": "GHADAMES", "fluid": "Oil", "api": 40, "lat": 30.01, "lon":  9.35},
    {"name": "Al Jurf",            "basin": "OFFSHORE", "fluid": "Oil", "api": 32, "lat": 32.50, "lon": 12.80},
]
 
# ── Full per-basin petrophysical defaults ────────────────────
#
# Every key below is accessed by PetrophysicsEngine.run().
# Missing keys → KeyError crash at runtime.
#
# rho_fluid            g/cc  – formation water density (1.05 = slightly saline)
# rsh                  ohm-m – shale resistivity (used in Simandoux Sw)
# vsh_method                 – 'larionov_young' | 'larionov_old' | 'linear'
# hydrostatic_gradient psi/ft – 0.433 fresh / 0.465 saline
# normal_dt_surface    µs/ft – Eaton normal compaction at surface
# normal_dt_exp              – compaction exponent (negative)
# typical_api / gor          – informational strings used in AI prompts
 
_BASIN_DEFAULTS: Dict[str, Dict] = {
    "SIRTE": {
        "gr_clean"             : 12.0,
        "gr_shale"             : 90.0,
        "rho_matrix"           : 2.71,   # limestone (Intisar / Ruaga carbonates)
        "rho_fluid"            : 1.05,   # slightly saline
        "rw"                   : 0.025,  # Paleocene brine resistivity
        "rsh"                  : 1.5,
        "vsh_method"           : "larionov_young",
        "overburden_gradient"  : 0.95,
        "hydrostatic_gradient" : 0.433,
        "normal_dt_surface"    : 130.0,
        "normal_dt_exp"        : -0.00020,
        "typical_api"          : "36–44° (light crude)",
        "typical_gor"          : "500–2500 scf/STB",
    },
    "GHADAMES": {
        "gr_clean"             : 22.0,
        "gr_shale"             : 105.0,
        "rho_matrix"           : 2.65,   # Paleozoic sandstone
        "rho_fluid"            : 1.00,
        "rw"                   : 0.042,
        "rsh"                  : 2.0,
        "vsh_method"           : "larionov_old",
        "overburden_gradient"  : 1.00,
        "hydrostatic_gradient" : 0.433,
        "normal_dt_surface"    : 120.0,
        "normal_dt_exp"        : -0.00022,
        "typical_api"          : "45–55° (condensate/gas)",
        "typical_gor"          : "5000–20000 scf/STB",
    },
    "MURZUQ": {
        "gr_clean"             : 18.0,
        "gr_shale"             : 92.0,
        "rho_matrix"           : 2.65,   # Ordovician glaciogenic sands
        "rho_fluid"            : 1.00,
        "rw"                   : 0.052,
        "rsh"                  : 2.2,
        "vsh_method"           : "larionov_young",
        "overburden_gradient"  : 0.98,
        "hydrostatic_gradient" : 0.433,
        "normal_dt_surface"    : 125.0,
        "normal_dt_exp"        : -0.00021,
        "typical_api"          : "38–42° (El Sharara crude)",
        "typical_gor"          : "300–800 scf/STB",
    },
    "OFFSHORE": {
        "gr_clean"             : 20.0,
        "gr_shale"             : 90.0,
        "rho_matrix"           : 2.70,
        "rho_fluid"            : 1.03,   # seawater-influenced
        "rw"                   : 0.030,
        "rsh"                  : 1.8,
        "vsh_method"           : "larionov_young",
        "overburden_gradient"  : 0.92,
        "hydrostatic_gradient" : 0.465,  # saline
        "normal_dt_surface"    : 135.0,
        "normal_dt_exp"        : -0.00018,
        "typical_api"          : "32–38°",
        "typical_gor"          : "400–1500 scf/STB",
    },
    "KUFRA": {
        "gr_clean"             : 20.0,
        "gr_shale"             : 95.0,
        "rho_matrix"           : 2.65,
        "rho_fluid"            : 1.00,
        "rw"                   : 0.060,
        "rsh"                  : 2.5,
        "vsh_method"           : "larionov_young",
        "overburden_gradient"  : 0.95,
        "hydrostatic_gradient" : 0.433,
        "normal_dt_surface"    : 125.0,
        "normal_dt_exp"        : -0.00020,
        "typical_api"          : "Unknown (frontier)",
        "typical_gor"          : "Unknown",
    },
    "CYRENAICA": {
        "gr_clean"             : 15.0,
        "gr_shale"             : 88.0,
        "rho_matrix"           : 2.71,
        "rho_fluid"            : 1.03,
        "rw"                   : 0.028,
        "rsh"                  : 1.6,
        "vsh_method"           : "larionov_young",
        "overburden_gradient"  : 0.93,
        "hydrostatic_gradient" : 0.433,
        "normal_dt_surface"    : 128.0,
        "normal_dt_exp"        : -0.00019,
        "typical_api"          : "35–42°",
        "typical_gor"          : "600–2000 scf/STB",
    },
}
 
# ── Reservoir quality cutoffs per lithology type ─────────────
LIBYAN_CUTOFFS = {
    "SIRTE_CARBONATE": {
        "phi_min" : 0.06,
        "sw_max"  : 0.55,
        "vsh_max" : 0.30,
        "perm_min": 0.05,
    },
    "GHADAMES_CLASTIC": {
        "phi_min" : 0.08,
        "sw_max"  : 0.55,
        "vsh_max" : 0.35,
        "perm_min": 0.10,
    },
    "MURZUQ_CLASTIC": {
        "phi_min" : 0.08,
        "sw_max"  : 0.55,
        "vsh_max" : 0.35,
        "perm_min": 0.10,
    },
}
 
 
def get_basin_defaults(basin: str) -> Dict:
    """Return a full copy of basin defaults. Falls back to SIRTE if unknown."""
    key = basin.strip().upper()
    return dict(_BASIN_DEFAULTS.get(key, _BASIN_DEFAULTS["SIRTE"]))
 
