"""
Project_QLE/pipeline.py
──────────────────
Main orchestration pipeline.

Connects parsers → analysis → AI into a single callable.

Usage
─────
    from Project_QLE.pipeline import GeoAIPipeline

    pipe = GeoAIPipeline(project_name="Block-7 Exploration")
    pipe.add_las("well_A.las")
    pipe.add_las("well_B.las")
    report = pipe.run()
    print(report.ai_summary)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.progress import track

from Project_QLE.core.models import InterpretationReport, WellLog
from Project_QLE.parsers      import parse_las, parse_file, detect_file_type
from Project_QLE.core.models  import FileType
from Project_QLE.analysis     import (
    PetrophysicsEngine,
    KMeansFacies,
    RuleBasedFacies,
    labels_to_zones,
    batch_stats,
    correlate_well_suite,
    correlate_markers_across_wells,
    build_reservoir_summary,
)

logger  = logging.getLogger(__name__)
console = Console()


class GeoAIPipeline:
    """
    Full interpretation pipeline for oil exploration data.

    Parameters
    ----------
    project_name    : Name of the exploration project.
    use_ai          : If True and ANTHROPIC_API_KEY is set, call Claude for narratives.
    facies_method   : 'rules' | 'kmeans' (default: 'kmeans')
    """

    def __init__(
        self,
        project_name: str    = "Unnamed Project",
        use_ai: bool         = True,
        facies_method: str   = "kmeans",
        api_key: Optional[str] = None,
    ):
        self.project_name  = project_name
        self.use_ai        = use_ai
        self.facies_method = facies_method
        self.api_key       = api_key

        self._wells       : List[WellLog]        = []
        self._extra_files : List[Path]           = []

    # ─────────────────────────────────────────
    #  Input registration
    # ─────────────────────────────────────────

    def add_las(self, path: str | Path) -> "GeoAIPipeline":
        """Parse and register a LAS file."""
        well = parse_las(path)
        self._wells.append(well)
        console.print(f"[green]✓[/green] Loaded well [bold]{well.header.well_name}[/bold]"
                      f" ({len(well.curves)} curves, "
                      f"{well.header.start_depth:.0f}–{well.header.stop_depth:.0f} m)")
        return self

    def add_file(self, path: str | Path) -> "GeoAIPipeline":
        """Register any other supported file (PDF, CSV, XML, etc.)."""
        self._extra_files.append(Path(path))
        return self

    # ─────────────────────────────────────────
    #  Run
    # ─────────────────────────────────────────

    def run(self) -> InterpretationReport:
        """Execute the full pipeline and return an InterpretationReport."""
        console.rule("[bold blue]Project_QLE Interpretation Pipeline")
        report = InterpretationReport(
            project_name = self.project_name,
            wells        = self._wells,
        )

        if not self._wells:
            console.print("[yellow]⚠ No wells loaded – returning empty report.[/yellow]")
            return report

        # ── 1. Petrophysics ──────────────────
        console.print("\n[cyan]Step 1: Petrophysical analysis[/cyan]")
        petro_dfs = {}
        for well in track(self._wells, description="Computing petrophysics …"):
            try:
                engine = PetrophysicsEngine(well)
                petro_dfs[well.header.well_name] = engine.run()
                # Update well's internal df with derived columns
                well.df = petro_dfs[well.header.well_name]
            except Exception as e:
                logger.error("Petrophysics failed for %s: %s", well.header.well_name, e)
                report.warnings.append(f"Petrophysics error ({well.header.well_name}): {e}")

        # ── 2. Facies classification ─────────
        console.print("\n[cyan]Step 2: Facies classification[/cyan]")
        for well in track(self._wells, description="Classifying facies …"):
            df = petro_dfs.get(well.header.well_name, well.df)
            if df is None or df.empty:
                continue
            try:
                if self.facies_method == "rules":
                    clf = RuleBasedFacies()
                    facies_labels = clf.classify(df)
                else:
                    clf = KMeansFacies(n_clusters=5)
                    facies_labels = clf.fit_predict(df)
                df["FACIES"] = facies_labels
                depth = well.get_depth()
                if depth is not None:
                    zones = labels_to_zones(depth, facies_labels)
                else:
                    zones = []
            except Exception as e:
                logger.error("Facies error for %s: %s", well.header.well_name, e)
                report.warnings.append(f"Facies error ({well.header.well_name}): {e}")
                zones = []

            # ── 3. Reservoir characterisation ─
            try:
                rs = build_reservoir_summary(well, df, zones)
                report.reservoirs.append(rs)
            except Exception as e:
                logger.error("Reservoir summary error for %s: %s", well.header.well_name, e)
                report.warnings.append(f"Reservoir error ({well.header.well_name}): {e}")

        # ── 4. Statistical analysis ──────────
        console.print("\n[cyan]Step 3: Statistical analysis[/cyan]")
        for well in track(self._wells, description="Computing statistics …"):
            try:
                stats = batch_stats(well, ["GR", "RHOB", "NPHI", "PHIE", "SW"])
                report.statistics.extend(stats)
            except Exception as e:
                report.warnings.append(f"Stats error ({well.header.well_name}): {e}")

        # ── 5. Cross-well correlation ─────────
        if len(self._wells) >= 2:
            console.print("\n[cyan]Step 4: Cross-well log correlation[/cyan]")
            try:
                report.correlations = correlate_well_suite(
                    self._wells, curves=["GR", "RHOB"]
                )
                console.print(f"  [green]✓[/green] {len(report.correlations)} correlation pairs computed")
            except Exception as e:
                report.warnings.append(f"Correlation error: {e}")

        # ── 6. AI interpretation ─────────────
        if self.use_ai:
            console.print("\n[cyan]Step 5: AI interpretation (Claude)[/cyan]")
            try:
                from Project_QLE.ai import AIInterpreter
                ai = AIInterpreter(api_key=self.api_key)

                for rs in track(report.reservoirs, description="Generating AI narratives …"):
                    stats_for_well = [s for s in report.statistics if s.well == rs.well_name]
                    rs.ai_narrative = ai.interpret_reservoir(rs, stats_for_well)

                if len(report.reservoirs) > 0:
                    report.ai_summary = ai.summarise_report(report)

            except Exception as e:
                logger.error("AI interpretation failed: %s", e)
                report.warnings.append(f"AI error: {e}")

        # ── Summary ───────────────────────────
        console.rule()
        console.print(
            f"[bold green]Pipeline complete[/bold green]  "
            f"Wells: {len(report.wells)} | "
            f"Reservoirs: {len(report.reservoirs)} | "
            f"Correlations: {len(report.correlations)} | "
            f"Warnings: {len(report.warnings)}"
        )
        if report.warnings:
            for w in report.warnings:
                console.print(f"  [yellow]⚠[/yellow] {w}")

        return report