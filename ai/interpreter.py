"""
Project_QLE/ai/interpreter.py
─────────────────────────
AI-powered geological interpretation using Claude.

Capabilities
────────────
- Narrative reservoir description from numeric results
- Anomaly explanation
- Cross-well correlation commentary
- Risk / uncertainty commentary
- Natural language query → petrophysical insight
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

try:
    import anthropic
except ImportError:
    raise ImportError("Install anthropic SDK: pip install anthropic")

from Project_QLE.core.models import (
    InterpretationReport, ReservoirSummary, StatisticalResult,
    CorrelationResult, WellLog,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  Prompts
# ─────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert petroleum geologist and petrophysicist with 30 years of experience 
in well log interpretation, reservoir characterisation, and seismic analysis.

When presented with numerical petrophysical data, you:
1. Provide clear, accurate geological interpretations.
2. Identify key reservoir intervals and fluid contacts.
3. Flag data quality issues or anomalies that need attention.
4. Estimate reservoir quality and producibility.
5. Give concise, professional summaries suitable for exploration reports.

Always structure your response clearly. 
Highlight confidence levels and important uncertainties.
Use standard oilfield terminology.
"""

_RESERVOIR_TEMPLATE = """\
Interpret the following reservoir characterisation data for well {well_name}:

PETROPHYSICAL SUMMARY
──────────────────────
Net Pay             : {net_pay_m:.1f} m
Average Porosity    : {avg_phi:.1%}
Average Sw          : {avg_sw:.1%}
Average Permeability: {avg_perm:.1f} mD
OWC / Fluid Contact : {owc}

ZONE BREAKDOWN
──────────────
{zone_table}

STATISTICAL CONTEXT
────────────────────
{stats_context}

Please provide:
1. Reservoir quality assessment (poor / fair / good / excellent)
2. Fluid type and saturation interpretation
3. Key risks and uncertainties
4. Recommended follow-up actions
5. Overall exploration potential (1-sentence summary)
"""

_CORRELATION_TEMPLATE = """\
Cross-well correlation results for {n_wells} wells:

{correlation_table}

Formation tops identified:
{tops_table}

Provide:
1. Stratigraphic continuity assessment
2. Lateral facies variation commentary
3. Structural interpretation implications
4. Confidence in correlations
"""

_ANOMALY_TEMPLATE = """\
The following anomalies were detected in the well-log data:

{anomalies}

For each anomaly, provide:
1. Probable geological cause
2. Data quality vs. geological origin assessment
3. Recommended action (re-process / accept / flag)
"""


# ─────────────────────────────────────────────
#  Client wrapper
# ─────────────────────────────────────────────

class AIInterpreter:
    """
    Wraps the Anthropic Claude API to provide geological AI interpretation.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-opus-4-5"):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "Anthropic API key required. "
                "Set ANTHROPIC_API_KEY env var or pass api_key=..."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model   = model

    def _call(self, user_message: str, max_tokens: int = 1500) -> str:
        response = self._client.messages.create(
            model      = self.model,
            max_tokens = max_tokens,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    # ──────────────────────────────────────────
    #  Reservoir narrative
    # ──────────────────────────────────────────

    def interpret_reservoir(
        self,
        summary: ReservoirSummary,
        stats: Optional[List[StatisticalResult]] = None,
    ) -> str:
        """Generate narrative interpretation of a ReservoirSummary."""

        # Build zone table
        zone_rows = []
        for z in summary.zones[:15]:   # cap at 15 rows
            zone_rows.append(
                f"  {z.top:8.1f}–{z.base:8.1f} m | {z.facies.value:<12} | "
                f"φ={z.porosity:.2f if z.porosity else 'N/A'} | "
                f"Sw={z.sw:.2f if z.sw else 'N/A'} | "
                f"Fluid={z.fluid.value}"
            )
        zone_table = "\n".join(zone_rows) or "  (no zones)"

        # Stats context
        if stats:
            lines = []
            for s in stats[:6]:
                lines.append(
                    f"  {s.curve:<8} mean={s.mean:.2f} std={s.std:.2f} "
                    f"P10={s.p10:.2f} P90={s.p90:.2f}"
                )
            stats_context = "\n".join(lines)
        else:
            stats_context = "  (not provided)"

        prompt = _RESERVOIR_TEMPLATE.format(
            well_name  = summary.well_name,
            net_pay_m  = summary.net_pay_m or 0,
            avg_phi    = summary.avg_porosity or 0,
            avg_sw     = summary.avg_sw or 0,
            avg_perm   = summary.avg_perm_mD or 0,
            owc        = f"{summary.fluid_contact:.1f} m" if summary.fluid_contact else "Not detected",
            zone_table = zone_table,
            stats_context = stats_context,
        )

        logger.info("Calling AI interpreter for well %s …", summary.well_name)
        narrative = self._call(prompt, max_tokens=1200)
        summary.ai_narrative = narrative
        return narrative

    # ──────────────────────────────────────────
    #  Correlation interpretation
    # ──────────────────────────────────────────

    def interpret_correlations(
        self,
        correlations: List[CorrelationResult],
        tops_df=None,
    ) -> str:
        corr_rows = [
            f"  {c.well_a} vs {c.well_b} | {c.curve} | r={c.pearson_r:.3f} | lag={c.lag_m:.1f} m"
            for c in correlations
        ]
        corr_table = "\n".join(corr_rows) or "  (none)"

        tops_table = "  (none)"
        if tops_df is not None and not tops_df.empty:
            tops_table = tops_df.to_string(index=False)

        prompt = _CORRELATION_TEMPLATE.format(
            n_wells           = len({c.well_a for c in correlations} | {c.well_b for c in correlations}),
            correlation_table = corr_table,
            tops_table        = tops_table,
        )
        return self._call(prompt)

    # ──────────────────────────────────────────
    #  Anomaly explanation
    # ──────────────────────────────────────────

    def explain_anomalies(self, anomaly_descriptions: List[str]) -> str:
        anomaly_text = "\n".join(f"- {a}" for a in anomaly_descriptions)
        return self._call(_ANOMALY_TEMPLATE.format(anomalies=anomaly_text))

    # ──────────────────────────────────────────
    #  Free-form geological Q&A
    # ──────────────────────────────────────────

    def ask(self, question: str, context: Optional[str] = None) -> str:
        """Natural language geological question with optional data context."""
        prompt = question
        if context:
            prompt = f"Context:\n{context}\n\nQuestion: {question}"
        return self._call(prompt)

    # ──────────────────────────────────────────
    #  Full report AI summary
    # ──────────────────────────────────────────

    def summarise_report(self, report: InterpretationReport) -> str:
        """Generate executive summary for the full InterpretationReport."""
        n_wells = len(report.wells)
        n_zones = sum(len(r.zones) for r in report.reservoirs)
        net_pays = [r.net_pay_m for r in report.reservoirs if r.net_pay_m]

        prompt = f"""\
Project: {report.project_name}
Wells analysed: {n_wells}
Reservoir zones identified: {n_zones}
Net pay range: {min(net_pays):.1f}–{max(net_pays):.1f} m (across wells)

Reservoir summaries:
{chr(10).join(f"  {r.well_name}: net_pay={r.net_pay_m:.1f}m, φ={r.avg_porosity:.2f}, Sw={r.avg_sw:.2f}" for r in report.reservoirs)}

Cross-well correlations computed: {len(report.correlations)}

Write a concise executive summary (3–4 paragraphs) covering:
1. Overall exploration potential
2. Key reservoir characteristics
3. Main risks and uncertainties
4. Recommended next steps
"""
        summary = self._call(prompt, max_tokens=800)
        report.ai_summary = summary
        return summary