"""Libyan basin defaults and field metadata for Project_QLE."""

from __future__ import annotations

from typing import Dict, List

LIBYAN_BASINS: Dict[str, str] = {
    "SIRTE": "Sirte Basin",
    "GHADAMES": "Ghadames Basin",
    "MURZUQ": "Murzuq Basin",
    "OFFSHORE": "Libyan Offshore",
}

LIBYAN_FIELDS: List[Dict[str, object]] = [
    {
        "name": "Waha Oilfield",
        "basin": "SIRTE",
        "fluid": "Oil",
        "api": 32.1,
        "lat": 29.723,
        "lon": 20.169,
    },
    {
        "name": "Gialo Oilfield",
        "basin": "GHADAMES",
        "fluid": "Oil",
        "api": 40.5,
        "lat": 30.012,
        "lon": 9.354,
    },
    {
        "name": "Agordat Field",
        "basin": "MURZUQ",
        "fluid": "Oil",
        "api": 35.2,
        "lat": 24.517,
        "lon": 12.279,
    },
    {
        "name": "Eastern Offshore Block",
        "basin": "OFFSHORE",
        "fluid": "Oil",
        "api": 38.7,
        "lat": 28.491,
        "lon": 18.712,
    },
]

_BASIN_DEFAULTS: Dict[str, Dict[str, float]] = {
    "SIRTE": {
        "gr_clean": 15.0,
        "gr_shale": 95.0,
        "rho_matrix": 2.71,
        "rw": 0.06,
        "overburden_gradient": 0.45,
    },
    "GHADAMES": {
        "gr_clean": 40.0,
        "gr_shale": 120.0,
        "rho_matrix": 2.65,
        "rw": 0.08,
        "overburden_gradient": 0.50,
    },
    "MURZUQ": {
        "gr_clean": 30.0,
        "gr_shale": 110.0,
        "rho_matrix": 2.68,
        "rw": 0.07,
        "overburden_gradient": 0.48,
    },
    "OFFSHORE": {
        "gr_clean": 20.0,
        "gr_shale": 90.0,
        "rho_matrix": 2.70,
        "rw": 0.04,
        "overburden_gradient": 0.43,
    },
}


def get_basin_defaults(basin: str) -> Dict[str, float]:
    key = basin.strip().upper()
    if key not in _BASIN_DEFAULTS:
        raise ValueError(f"Unknown basin: {basin}")
    return dict(_BASIN_DEFAULTS[key])
