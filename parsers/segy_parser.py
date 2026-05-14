"""
project_QLE/parsers/segy_parser.py
──────────────────────────────
Read SEG-Y seismic files into SeismicDataset objects.
Uses segyio under the hood.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

try:
    import segyio
except ImportError:
    raise ImportError("Install segyio: pip install segyio")

from project_QLE.core.models import FileType, ParsedFile, SeismicDataset, SeismicTrace

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Public functions
# ─────────────────────────────────────────────

def parse_segy(
    path: str | Path,
    max_traces: Optional[int] = None,
    ignore_geometry: bool = True,
) -> SeismicDataset:
    """
    Parse a SEG-Y file.

    Parameters
    ----------
    path           : Path to the .segy / .sgy file.
    max_traces     : If set, only load this many traces (useful for large surveys).
    ignore_geometry: Pass True for post-stack / 2-D where headers may be incomplete.

    Returns
    -------
    SeismicDataset
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    logger.info("Opening SEG-Y: %s", path.name)

    traces: List[SeismicTrace] = []

    with segyio.open(str(path), "r", ignore_geometry=ignore_geometry) as f:
        f.mmap()  # memory-map for speed

        n_traces    = f.tracecount
        n_samples   = len(f.samples)
        sample_rate = segyio.tools.dt(f) / 1_000_000  # µs → s
        delay       = float(f.header[0][segyio.TraceField.DelayRecordingTime]) / 1000  # ms → s

        meta = {
            "n_traces"    : n_traces,
            "n_samples"   : n_samples,
            "sample_rate_s": sample_rate,
            "delay_s"     : delay,
            "format"      : int(f.bin[segyio.BinField.SEGYRevision]),
            "text_header" : segyio.tools.wrap(f.text[0]),
        }

        load_n = min(n_traces, max_traces) if max_traces else n_traces
        logger.info("Loading %d / %d traces …", load_n, n_traces)

        for i in range(load_n):
            h = f.header[i]
            trace = SeismicTrace(
                trace_number = i + 1,
                inline    = int(h.get(segyio.TraceField.INLINE_3D,   0)),
                crossline = int(h.get(segyio.TraceField.CROSSLINE_3D, 0)),
                x_coord   = float(h.get(segyio.TraceField.CDP_X,  0)),
                y_coord   = float(h.get(segyio.TraceField.CDP_Y,  0)),
                samples   = f.trace[i].tolist(),
                sample_rate = sample_rate,
                delay     = delay,
            )
            traces.append(trace)

    dataset = SeismicDataset(
        source      = path,
        n_traces    = n_traces,
        n_samples   = n_samples,
        sample_rate = sample_rate,
        traces      = traces,
        metadata    = meta,
    )
    logger.info("SEG-Y loaded: %d traces × %d samples @ %.4f s", n_traces, n_samples, sample_rate)
    return dataset


def segy_amplitude_section(dataset: SeismicDataset) -> np.ndarray:
    """
    Return a 2-D numpy array (traces × samples) for display / analysis.
    """
    if not dataset.traces:
        return np.array([])
    return np.array([t.samples for t in dataset.traces])


def segy_to_parsed_file(path: str | Path, max_traces: Optional[int] = 500) -> ParsedFile:
    ds = parse_segy(path, max_traces=max_traces)
    return ParsedFile(
        source_path = Path(path),
        file_type   = FileType.SEGY,
        metadata    = ds.metadata,
        extra       = {"seismic_dataset": ds},
    )