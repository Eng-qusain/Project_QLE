"""
Project_QLE/ai/gemini_interpreter.py
──────────────────────────────────────
AI-powered geological interpretation using Google Gemini.
All prompts are calibrated for Libyan petroleum geology.

Setup
─────
    pip install google-generativeai
    export GEMINI_API_KEY="your-key-here"

Or pass api_key= directly.
"""
from __future__ import annotations
import logging
import os
from typing import List, Optional

from Project_QLE.core.models import (
    InterpretationReport, ReservoirSummary,
    StatisticalResult, CorrelationResult,
)
from Project_QLE.core.libya_geology import get_basin_defaults, LIBYAN_BASINS

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. Run: pip install google-generativeai")


# ─────────────────────────────────────────────
#  System prompt – Libya-specific
# ─────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior petroleum geologist and petrophysicist specialising in North African \
and Libyan petroleum systems. You have 30 years of experience working in:

  • Sirte Basin – Cretaceous/Paleocene carbonate reservoirs (Intisar, Ruaga, Sabil, Sarir)
  • Ghadames Basin – Paleozoic clastic reservoirs (Acacus, Tiguentourine, Mamuniyat)
  • Murzuq Basin – Ordovician glaciogenic sandstones (El Sharara, El Feel fields)
  • Offshore Mediterranean block exploration

When interpreting data you:
1. Reference Libyan formation names and known field analogues where appropriate.
2. Apply North African structural context (Tethyan margin, inversion tectonics, basement highs).
3. Use NOC (National Oil Corporation) style reporting conventions.
4. Clearly state reservoir quality classes: Excellent (φ>20%, k>100mD), Good (φ>12%, k>10mD),
   Fair (φ>8%, k>1mD), Poor (φ<8%, k<1mD) — adjusted for carbonates.
5. Comment on Libya-specific risks: diagenesis in Sirte carbonates, cementation in Paleozoic sands,
   overpressure in deep Ghadames wells, compartmentalisation in Murzuq Ordovician.
6. Always give a concise exploration risk rating: LOW / MODERATE / HIGH.

Respond professionally. Use structured sections. Be concise but complete.
"""


# ─────────────────────────────────────────────
#  Prompt templates
# ─────────────────────────────────────────────

def _reservoir_prompt(summary: ReservoirSummary,
                       stats: Optional[List[StatisticalResult]] = None) -> str:
    basin_info = get_basin_defaults(summary.basin)

    zone_rows = "\n".join(
        f"  {z.top:8.1f}–{z.base:8.1f} m | {z.facies.value:<12} | "
        f"φ={'%.3f'%z.porosity if z.porosity else 'N/A'} | "
        f"Sw={'%.3f'%z.sw if z.sw else 'N/A'} | "
        f"k={'%.1f'%z.perm_mD if z.perm_mD else 'N/A'} mD | "
        f"PP={'%d'%z.pressure_psi if z.pressure_psi else 'N/A'} psi | "
        f"Fluid={z.fluid.value}"
        for z in summary.zones[:20]
    ) or "  (no zones)"

    stats_txt = ""
    if stats:
        stats_txt = "\n".join(
            f"  {s.curve:<8} n={s.n} mean={s.mean:.2f} std={s.std:.2f} "
            f"P10={s.p10:.2f} P50={s.p50:.2f} P90={s.p90:.2f} skew={s.skewness:.2f}"
            for s in stats[:8]
        )

    return f"""
WELL RESERVOIR INTERPRETATION REQUEST
======================================
Well Name    : {summary.well_name}
Basin        : {LIBYAN_BASINS.get(summary.basin, summary.basin)}
Typical API  : {basin_info.get('typical_api', 'Unknown')}
Typical GOR  : {basin_info.get('typical_gor', 'Unknown')}

PETROPHYSICAL RESULTS
──────────────────────
Net Pay (m)         : {summary.net_pay_m:.1f if summary.net_pay_m else 'N/A'}
Avg Porosity (PHIE) : {f'{summary.avg_porosity:.1%}' if summary.avg_porosity else 'N/A'}
Avg Water Sat (Sw)  : {f'{summary.avg_sw:.1%}' if summary.avg_sw else 'N/A'}
Avg Permeability    : {f'{summary.avg_perm_mD:.1f} mD' if summary.avg_perm_mD else 'N/A'}
Fluid Contact (OWC/GOC depth): {f'{summary.fluid_contact:.1f} m' if summary.fluid_contact else 'Not detected'}

ZONE TABLE (top → base)
────────────────────────
{zone_rows}

LOG STATISTICS
───────────────
{stats_txt or '  (not provided)'}

REQUESTED OUTPUT
─────────────────
1. Reservoir quality class and justification
2. Fluid type and saturation interpretation
3. Pressure regime (normal / overpressured / underpressured)
4. Libyan formation analogue (if recognisable)
5. Key geological risks specific to this basin
6. Exploration risk rating: LOW / MODERATE / HIGH
7. One-paragraph executive summary
"""


def _correlation_prompt(correlations: List[CorrelationResult], tops_text: str = "") -> str:
    rows = "\n".join(
        f"  {c.well_a:<20} vs {c.well_b:<20} | {c.curve:<8} | r={c.pearson_r:.3f} | lag={c.lag_m:.1f} m"
        for c in correlations
    )
    return f"""
CROSS-WELL LOG CORRELATION – LIBYA
====================================
{rows}

Formation Tops Picked:
{tops_text or '  (not available)'}

Please provide:
1. Stratigraphic continuity assessment across wells
2. Lateral facies variation and depositional interpretation
3. Structural implications (dip, faulting, compartmentalisation)
4. Correlation confidence (High / Medium / Low) and reasoning
5. Recommended additional data or actions
"""


def _report_prompt(report: InterpretationReport) -> str:
    wells_summary = "\n".join(
        f"  {r.well_name:<25} | basin={r.basin:<10} | "
        f"net_pay={'%.1f m'%r.net_pay_m if r.net_pay_m else 'N/A':<8} | "
        f"φ={'%.2f'%r.avg_porosity if r.avg_porosity else 'N/A':<6} | "
        f"Sw={'%.2f'%r.avg_sw if r.avg_sw else 'N/A'}"
        for r in report.reservoirs
    )
    return f"""
PROJECT_QLE – EXPLORATION REPORT SUMMARY
==========================================
Project      : {report.project_name}
Basin        : {LIBYAN_BASINS.get(report.basin, report.basin)}
Wells        : {len(report.wells)}
Reservoirs   : {len(report.reservoirs)}
Correlations : {len(report.correlations)}
Date         : {report.created_at.strftime('%Y-%m-%d')}

WELL RESULTS
─────────────
{wells_summary or '  (none)'}

Please write a professional 4-paragraph executive summary covering:
1. Overall exploration potential and key reservoir findings
2. Reservoir quality and fluid system interpretation (Libya-specific context)
3. Main geological risks and uncertainties
4. Recommended next steps (additional wells, seismic, testing programme)

End with: OVERALL EXPLORATION POTENTIAL: [LOW / MODERATE / HIGH / VERY HIGH]
"""


# ─────────────────────────────────────────────
#  Interpreter class
# ─────────────────────────────────────────────

class GeminiInterpreter:
    """
    Gemini-powered geological interpreter for Project_QLE.

    Parameters
    ----------
    api_key : str, optional  (falls back to GEMINI_API_KEY env var)
    model   : Gemini model name (default: gemini-1.5-flash – fast & capable)
    """

    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = "gemini-1.5-flash"):
        if not GEMINI_AVAILABLE:
            raise ImportError("Run: pip install google-generativeai")

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "Gemini API key required.\n"
                "Set GEMINI_API_KEY environment variable or pass api_key=..."
            )

        genai.configure(api_key=key)
        self._model = genai.GenerativeModel(
            model_name    = model,
            system_instruction = _SYSTEM_PROMPT,
        )
        self.model_name = model

    def _call(self, prompt: str, max_tokens: int = 1500) -> str:
        """Single-turn call to Gemini."""
        try:
            response = self._model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.3,   # low temp = more deterministic / professional
                ),
            )
            return response.text
        except Exception as e:
            logger.error("Gemini API error: %s", e)
            return f"[AI interpretation unavailable: {e}]"

    # ── Public methods ────────────────────────

    def interpret_reservoir(self,
                            summary: ReservoirSummary,
                            stats: Optional[List[StatisticalResult]] = None) -> str:
        """Full reservoir narrative for one well."""
        prompt = _reservoir_prompt(summary, stats)
        logger.info("Gemini: interpreting %s (%s)", summary.well_name, summary.basin)
        text = self._call(prompt, max_tokens=1200)
        summary.ai_narrative = text
        return text

    def interpret_correlations(self,
                                correlations: List[CorrelationResult],
                                tops_df=None) -> str:
        tops_text = tops_df.to_string(index=False) if (tops_df is not None and not tops_df.empty) else ""
        return self._call(_correlation_prompt(correlations, tops_text))

    def summarise_report(self, report: InterpretationReport) -> str:
        text = self._call(_report_prompt(report), max_tokens=900)
        report.ai_summary = text
        return text

    def ask(self, question: str, context: str = "") -> str:
        """Free-form geological Q&A."""
        prompt = f"{context}\n\nQuestion: {question}" if context else question
        return self._call(prompt, max_tokens=800)

    def explain_anomaly(self, description: str) -> str:
        prompt = f"""
The following anomaly was detected in a Libyan well log:

{description}

Explain:
1. Most likely geological cause (Libyan context)
2. Data quality vs. true geological origin assessment
3. Recommended action
"""
        return self._call(prompt, max_tokens=600)