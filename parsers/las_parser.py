"""
project_QLE/parsers/las_parser.py
────────────────────────────
Read LAS 1.2, 2.0, and 3.0 well-log files into WellLog objects.
Uses lasio under the hood, then maps to internal models.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

try:
    import lasio
except ImportError:
    raise ImportError("Install lasio: pip install lasio")

from project_QLE.core.models import (
    CurveType, FileType, ParsedFile,
    WellCurve, WellHeader, WellLog,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Mnemonic → CurveType map  (case-insensitive prefix match)
# ─────────────────────────────────────────────

_MNEMONIC_MAP: Dict[str, CurveType] = {
    "GR"   : CurveType.GR,
    "SP"   : CurveType.SP,
    "RT"   : CurveType.RT,
    "ILD"  : CurveType.RT,
    "LLD"  : CurveType.RT,
    "RHOB" : CurveType.RHOB,
    "RHOZ" : CurveType.RHOB,
    "NPHI" : CurveType.NPHI,
    "TNPH" : CurveType.NPHI,
    "DT"   : CurveType.DT,
    "DTC"  : CurveType.DT,
    "DTCO" : CurveType.DT,
    "CALI" : CurveType.CALI,
    "PE"   : CurveType.PE,
    "DEPT" : CurveType.DEPT,
    "DEPTH": CurveType.DEPT,
    "MD"   : CurveType.MD,
    "TVD"  : CurveType.TVD,
}


def _map_curve_type(mnemonic: str) -> CurveType:
    upper = mnemonic.upper()
    for key, ct in _MNEMONIC_MAP.items():
        if upper.startswith(key):
            return ct
    return CurveType.OTHER


# ─────────────────────────────────────────────
#  Header extraction
# ─────────────────────────────────────────────

def _extract_header(las: lasio.LASFile) -> WellHeader:
    def _get(section: str, mnemonic: str, default="") -> str:
        try:
            return str(las.header[section][mnemonic].value)
        except (KeyError, AttributeError):
            return default

    def _float(section: str, mnemonic: str) -> Optional[float]:
        val = _get(section, mnemonic)
        try:
            return float(val) if val else None
        except ValueError:
            return None

    return WellHeader(
        well_name  = _get("Well", "WELL") or _get("Well", "WN") or "UNKNOWN",
        uwi        = _get("Well", "UWI"),
        field      = _get("Well", "FLD"),
        company    = _get("Well", "COMP"),
        location   = _get("Well", "LOC"),
        latitude   = _float("Well", "LATI"),
        longitude  = _float("Well", "LONG"),
        kb_elev    = _float("Well", "KB"),
        td         = _float("Well", "TD"),
        start_depth= float(las.well.STRT.value) if hasattr(las.well, "STRT") else None,
        stop_depth = float(las.well.STOP.value) if hasattr(las.well, "STOP") else None,
        step       = float(las.well.STEP.value) if hasattr(las.well, "STEP") else None,
        null_value = float(las.well.NULL.value) if hasattr(las.well, "NULL") else -999.25,
    )


# ─────────────────────────────────────────────
#  Public function
# ─────────────────────────────────────────────

def parse_las(path: str | Path) -> WellLog:
    """
    Parse a LAS file and return a WellLog.

    Parameters
    ----------
    path : str or Path

    Returns
    -------
    WellLog
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    logger.info("Parsing LAS file: %s", path.name)
    las = lasio.read(str(path))

    header = _extract_header(las)
    null_val = header.null_value

    curves: Dict[str, WellCurve] = {}
    for curve_item in las.curves:
        mnemonic = curve_item.mnemonic.upper()
        data = np.where(
            np.isclose(curve_item.data, null_val, atol=0.01),
            np.nan,
            curve_item.data,
        ).tolist()

        curves[mnemonic] = WellCurve(
            mnemonic    = mnemonic,
            unit        = curve_item.unit or "",
            description = curve_item.descr or "",
            curve_type  = _map_curve_type(mnemonic),
            data        = data,
        )

    # Build convenience DataFrame
    df = las.df().rename_axis("DEPTH").reset_index()
    df.columns = [c.upper() for c in df.columns]
    df.replace(null_val, np.nan, inplace=True)

    well = WellLog(
        header  = header,
        curves  = curves,
        df      = df,
        source  = path,
    )
    logger.info(
        "Loaded well '%s': %d curves, depth %.1f–%.1f m",
        header.well_name,
        len(curves),
        header.start_depth or 0,
        header.stop_depth or 0,
    )
    return well


def las_to_parsed_file(path: str | Path) -> ParsedFile:
    """Wrap parse_las result into a generic ParsedFile for the pipeline."""
    well = parse_las(path)
    return ParsedFile(
        source_path=Path(path),
        file_type=FileType.LAS,
        dataframe=well.df,
        metadata={
            "well_name" : well.header.well_name,
            "n_curves"  : len(well.curves),
            "start_depth": well.header.start_depth,
            "stop_depth" : well.header.stop_depth,
        },
        extra={"well_log": well},
    )