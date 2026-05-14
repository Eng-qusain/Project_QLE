"""
project_QLE/core/models.py
────────────────────
Pydantic data models that flow through the entire pipeline.
Every parser, analyser, and AI module speaks this language.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────

class FileType(str, Enum):
    PDF  = "pdf"
    DOCX = "docx"
    XML  = "xml"
    JPG  = "jpg"
    CSV  = "csv"
    LAS  = "las"
    SEGY = "segy"
    UNKNOWN = "unknown"


class CurveType(str, Enum):
    """Standard well-log curve mnemonics (extendable)."""
    GR   = "GR"    # Gamma Ray
    SP   = "SP"    # Spontaneous Potential
    RT   = "RT"    # True Resistivity
    RHOB = "RHOB"  # Bulk Density
    NPHI = "NPHI"  # Neutron Porosity
    DT   = "DT"    # Sonic / Delta-T
    CALI = "CALI"  # Caliper
    PE   = "PE"    # Photoelectric Factor
    DEPT = "DEPT"  # Depth
    MD   = "MD"    # Measured Depth
    TVD  = "TVD"   # True Vertical Depth
    OTHER = "OTHER"


class Facies(str, Enum):
    SANDSTONE  = "Sandstone"
    SHALE      = "Shale"
    LIMESTONE  = "Limestone"
    DOLOMITE   = "Dolomite"
    COAL       = "Coal"
    ANHYDRITE  = "Anhydrite"
    SALT       = "Salt"
    UNKNOWN    = "Unknown"


class FluidType(str, Enum):
    OIL   = "Oil"
    GAS   = "Gas"
    WATER = "Water"
    DRY   = "Dry"
    UNKNOWN = "Unknown"


# ─────────────────────────────────────────────
#  Raw parsed file container
# ─────────────────────────────────────────────

class ParsedFile(BaseModel):
    """Generic container returned by any parser."""
    source_path : Path
    file_type   : FileType
    raw_text    : Optional[str]          = None
    dataframe   : Optional[Any]          = None   # pd.DataFrame (not serialisable natively)
    metadata    : Dict[str, Any]         = Field(default_factory=dict)
    images      : List[bytes]            = Field(default_factory=list)
    extra       : Dict[str, Any]         = Field(default_factory=dict)
    parsed_at   : datetime               = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True


# ─────────────────────────────────────────────
#  Well / LAS data model
# ─────────────────────────────────────────────

class WellHeader(BaseModel):
    well_name  : str = "UNKNOWN"
    uwi        : Optional[str] = None
    field      : Optional[str] = None
    company    : Optional[str] = None
    location   : Optional[str] = None
    latitude   : Optional[float] = None
    longitude  : Optional[float] = None
    kb_elev    : Optional[float] = None   # Kelly bushing elevation (m)
    td         : Optional[float] = None   # Total depth (m)
    start_depth: Optional[float] = None
    stop_depth : Optional[float] = None
    step       : Optional[float] = None
    null_value : float = -999.25
    extra      : Dict[str, Any] = Field(default_factory=dict)


class WellCurve(BaseModel):
    mnemonic    : str
    unit        : str = ""
    description : str = ""
    curve_type  : CurveType = CurveType.OTHER
    data        : List[float] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    @property
    def array(self) -> np.ndarray:
        return np.array(self.data, dtype=float)


class WellLog(BaseModel):
    """Full well log data object (from LAS or synthetic)."""
    header   : WellHeader
    curves   : Dict[str, WellCurve]   = Field(default_factory=dict)
    df       : Optional[Any]          = None   # convenience DataFrame
    source   : Optional[Path]         = None

    class Config:
        arbitrary_types_allowed = True

    def get_depth(self) -> Optional[np.ndarray]:
        for key in ("DEPT", "MD", "DEPTH"):
            if key in self.curves:
                return self.curves[key].array
        return None

    def get_curve(self, mnemonic: str) -> Optional[np.ndarray]:
        if mnemonic in self.curves:
            return self.curves[mnemonic].array
        return None


# ─────────────────────────────────────────────
#  Seismic data model
# ─────────────────────────────────────────────

class SeismicTrace(BaseModel):
    trace_number : int
    inline       : Optional[int]   = None
    crossline    : Optional[int]   = None
    x_coord      : Optional[float] = None
    y_coord      : Optional[float] = None
    samples      : List[float]     = Field(default_factory=list)
    sample_rate  : float           = 0.004  # seconds
    delay        : float           = 0.0

    @property
    def time_axis(self) -> np.ndarray:
        n = len(self.samples)
        return np.arange(n) * self.sample_rate + self.delay


class SeismicDataset(BaseModel):
    source       : Path
    n_traces     : int
    n_samples    : int
    sample_rate  : float
    traces       : List[SeismicTrace] = Field(default_factory=list)
    metadata     : Dict[str, Any]     = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


# ─────────────────────────────────────────────
#  Interpretation results
# ─────────────────────────────────────────────

class ZoneInterval(BaseModel):
    """A depth interval with geological/petrophysical interpretation."""
    top          : float
    base         : float
    facies       : Facies        = Facies.UNKNOWN
    fluid        : FluidType     = FluidType.UNKNOWN
    vshale       : Optional[float] = None   # 0–1
    porosity     : Optional[float] = None   # 0–1 (PHIE)
    sw           : Optional[float] = None   # 0–1 water saturation
    perm_mD      : Optional[float] = None   # permeability estimate
    pressure_psi : Optional[float] = None   # pore pressure
    confidence   : float           = 0.0    # 0–1 AI confidence
    notes        : str             = ""


class ReservoirSummary(BaseModel):
    well_name     : str
    zones         : List[ZoneInterval]    = Field(default_factory=list)
    net_pay_m     : Optional[float]       = None
    avg_porosity  : Optional[float]       = None
    avg_sw        : Optional[float]       = None
    avg_perm_mD   : Optional[float]       = None
    fluid_contact : Optional[float]       = None   # OWC / GOC depth
    ai_narrative  : str                   = ""


class CorrelationResult(BaseModel):
    """Cross-well log correlation."""
    well_a      : str
    well_b      : str
    curve       : str
    pearson_r   : float
    lag_m       : float           = 0.0
    matched_zones: List[Tuple[float, float]] = Field(default_factory=list)


class StatisticalResult(BaseModel):
    curve       : str
    well        : str
    n           : int
    mean        : float
    std         : float
    min_val     : float
    max_val     : float
    p10         : float
    p50         : float
    p90         : float
    skewness    : float
    kurtosis    : float
    histogram   : Optional[Dict[str, List[float]]] = None   # bins + counts


class InterpretationReport(BaseModel):
    """Top-level output of a full interpretation run."""
    project_name  : str
    created_at    : datetime             = Field(default_factory=datetime.utcnow)
    wells         : List[WellLog]        = Field(default_factory=list)
    reservoirs    : List[ReservoirSummary] = Field(default_factory=list)
    correlations  : List[CorrelationResult] = Field(default_factory=list)
    statistics    : List[StatisticalResult] = Field(default_factory=list)
    seismic       : Optional[SeismicDataset] = None
    ai_summary    : str                  = ""
    warnings      : List[str]            = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True