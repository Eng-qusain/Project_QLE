"""
project_QLE/pipeline.py
────────────────────────
Main orchestration pipeline for Libya exploration data.

Usage
─────
    from project_QLE.pipeline import QLEPipeline

    pipe = QLEPipeline("Sirte Block 47", basin="SIRTE")
    pipe.add_las("WELL_A.las").add_las("WELL_B.las")
    report = pipe.run()
    print(report.ai_summary)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from project_QLE.core.models import InterpretationReport, WellLog
from project_QLE.parsers      import parse_las
from project_QLE.analysis     import (
    PetrophysicsEngine,
    KMeansFacies,
    RuleBasedFacies,
    labels_to_zones,
    batch_stats,
    correlate_well_suite,
    build_reservoir_summary,
)

logger = logging.getLogger(__name__)

# Standard log curves to run statistics on
_STAT_CURVES = ["GR", "RHOB", "NPHI", "RT", "PHIE", "SW", "PERM_mD"]


class QLEPipeline:
    """
    Project_QLE – Libya exploration interpretation pipeline.

    Parameters
    ----------
    project_name   : Display name for the project / report.
    basin          : Active Libyan basin ('SIRTE', 'GHADAMES', 'MURZUQ', …).
    use_ai         : If True, call Gemini for narrative interpretation.
    facies_method  : 'kmeans' (unsupervised) or 'rules' (deterministic).
    gemini_api_key : Gemini API key. Falls back to GEMINI_API_KEY env var.
    n_facies       : Number of KMeans clusters (ignored for rules method).
    """

    def __init__(
        self,
        project_name   : str           = "Project_QLE",
        basin          : str           = "SIRTE",
        use_ai         : bool          = True,
        facies_method  : str           = "kmeans",
        gemini_api_key : Optional[str] = None,
        n_facies       : int           = 5,
    ):
        self.project_name   = project_name
        self.basin          = basin.upper()
        self.use_ai         = use_ai
        self.facies_method  = facies_method
        self.gemini_api_key = gemini_api_key
        self.n_facies       = n_facies
        self._wells: List[WellLog] = []

    # ── Well registration ────────────────────────────────────

    def add_las(self, path: str | Path) -> "QLEPipeline":
        """Parse a LAS file and register the well."""
        well = parse_las(path)
        well.header.basin = self.basin
        self._wells.append(well)
        logger.info(
            "Loaded: %s  (%d curves, %.0f–%.0f m, basin=%s)",
            well.header.well_name, len(well.curves),
            well.header.start_depth or 0,
            well.header.stop_depth  or 0,
            self.basin,
        )
        return self

    def add_well(self, well: WellLog) -> "QLEPipeline":
        """Register a WellLog object that was already parsed (e.g. from the UI)."""
        well.header.basin = self.basin
        self._wells.append(well)
        return self

    # ── Pipeline execution ───────────────────────────────────

    def run(self) -> InterpretationReport:
        """Run the full interpretation pipeline and return an InterpretationReport."""
        _log = logger.info
        _log("=" * 55)
        _log("  Project_QLE Pipeline  │  %s", self.project_name)
        _log("=" * 55)

        report = InterpretationReport(
            project_name = self.project_name,
            basin        = self.basin,
            wells        = self._wells,
        )

        if not self._wells:
            logger.warning("No wells loaded – returning empty report.")
            return report

        petro_dfs = {}

        # ── Step 1: Petrophysics ─────────────────────────────
        _log("[1/5] Petrophysical analysis …")
        for well in self._wells:
            try:
                eng = PetrophysicsEngine(well, basin=self.basin)
                df  = eng.run()
                petro_dfs[well.header.well_name] = df
                well.df = df
            except Exception as exc:
                msg = f"Petrophys error ({well.header.well_name}): {exc}"
                report.warnings.append(msg)
                logger.error(msg)

        # ── Step 2: Facies + Reservoir ───────────────────────
        _log("[2/5] Facies classification & reservoir characterisation …")
        for well in self._wells:
            df = petro_dfs.get(well.header.well_name) or well.df
            if df is None or df.empty:
                continue
            try:
                if self.facies_method == "rules":
                    labels = RuleBasedFacies().classify(df)
                else:
                    labels = KMeansFacies(n_clusters=self.n_facies).fit_predict(df)

                df["FACIES"] = labels
                well.df      = df
                depth  = well.get_depth()
                zones  = labels_to_zones(depth, labels) if depth is not None else []
                rs     = build_reservoir_summary(well, df, zones)
                rs.basin = self.basin
                report.reservoirs.append(rs)
            except Exception as exc:
                msg = f"Facies/Reservoir error ({well.header.well_name}): {exc}"
                report.warnings.append(msg)
                logger.error(msg)

        # ── Step 3: Statistics ───────────────────────────────
        _log("[3/5] Statistical analysis …")
        for well in self._wells:
            try:
                report.statistics.extend(batch_stats(well, _STAT_CURVES))
            except Exception as exc:
                report.warnings.append(f"Stats error ({well.header.well_name}): {exc}")

        # ── Step 4: Cross-well correlation ───────────────────
        if len(self._wells) >= 2:
            _log("[4/5] Cross-well log correlation …")
            try:
                report.correlations = correlate_well_suite(
                    self._wells, curves=["GR", "RHOB"]
                )
                _log("  ✓ %d correlation pairs computed", len(report.correlations))
            except Exception as exc:
                report.warnings.append(f"Correlation error: {exc}")
        else:
            _log("[4/5] Cross-well correlation skipped (need ≥2 wells)")

        # ── Step 5: AI interpretation ────────────────────────
        if self.use_ai:
            _log("[5/5] AI interpretation (Gemini) …")
            try:
                from project_QLE.ai.gemini_interpreter import GeminiInterpreter
                ai = GeminiInterpreter(api_key=self.gemini_api_key)
                for rs in report.reservoirs:
                    stats_for = [s for s in report.statistics if s.well == rs.well_name]
                    ai.interpret_reservoir(rs, stats_for)
                if report.reservoirs:
                    ai.summarise_report(report)
            except Exception as exc:
                msg = f"AI error: {exc}"
                report.warnings.append(msg)
                logger.error(msg)
        else:
            _log("[5/5] AI interpretation skipped (use_ai=False)")

        # ── Done ─────────────────────────────────────────────
        _log("=" * 55)
        _log(
            "  ✓ Complete │ Wells:%d  Reservoirs:%d  Warnings:%d",
            len(report.wells), len(report.reservoirs), len(report.warnings),
        )
        for w in report.warnings:
            logger.warning("  ⚠ %s", w)

        return report