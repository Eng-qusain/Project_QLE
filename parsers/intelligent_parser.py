"""
project_QLE/parsers/intelligent_parser.py
──────────────────────────────────────────
AI-powered document intelligence for Project_QLE.

Extracts structured petrophysical data from:
  - PDF reports (well completion reports, mudlogs, core reports, DST reports)
  - CSV / Excel files with arbitrary column layouts
  - Raw text documents

Authors
───────
  Eng. Qusai Alnuaimat
  Dr. Lutfi Dugdug
  Waha Oil Company – Exploration Department

Usage
─────
    from project_QLE.parsers.intelligent_parser import DocumentIntelligence

    intel = DocumentIntelligence(gemini_api_key="AIza…")

    # From a PDF report
    result = intel.parse_pdf("well_completion_report.pdf")
    print(result.formation_tops)
    print(result.dst_tests)

    # From a CSV with unknown column names
    result = intel.parse_csv("core_data.csv")
    print(result.petro_dataframe)
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Result container ─────────────────────────────────────────

@dataclass
class DocumentExtraction:
    """Structured output from intelligent document parsing."""
    source_file     : str
    document_type   : str          = "unknown"   # 'well_report', 'core_data', 'dst_report', etc.
    raw_text        : str          = ""

    # Well identity
    well_names      : List[str]    = field(default_factory=list)
    basin           : str          = ""
    field_name      : str          = ""
    company         : str          = ""

    # Formation tops extracted from text
    formation_tops  : List[Dict]   = field(default_factory=list)
    # e.g. [{"formation_name": "Intisar C", "top_m": 2150.0, "base_m": 2210.0, "lithology": "Limestone"}]

    # DST results
    dst_tests       : List[Dict]   = field(default_factory=list)
    # e.g. [{"test_name": "DST-1", "depth_m": 2160.0, "flow_rate_bpd": 450.0, ...}]

    # Petrophysical values (tabular data)
    petro_dataframe : Optional[pd.DataFrame] = None

    # Any numeric values the AI identified
    key_values      : Dict[str, Any] = field(default_factory=dict)

    # AI narrative summary of the document
    ai_summary      : str          = ""

    # Warnings / issues during extraction
    warnings        : List[str]    = field(default_factory=list)


# ── Column type heuristics ───────────────────────────────────

_COLUMN_SYNONYMS: Dict[str, List[str]] = {
    "DEPTH":    ["depth", "md", "dept", "tvd", "depth_m", "depth(m)", "measured depth"],
    "GR":       ["gr", "gamma ray", "gamma_ray", "gammaray", "gapi"],
    "RHOB":     ["rhob", "density", "bulk density", "rhoz", "den"],
    "NPHI":     ["nphi", "neutron", "neutron porosity", "tnph", "phi_n"],
    "RT":       ["rt", "resistivity", "true resistivity", "ild", "lld", "res"],
    "DT":       ["dt", "sonic", "dtco", "dtc", "delta t", "travel time"],
    "PHIE":     ["phie", "porosity", "eff porosity", "phi_e", "phi"],
    "SW":       ["sw", "water saturation", "sw_archie", "sat"],
    "PERM_mD":  ["perm", "permeability", "k", "k_md", "perm_md"],
    "VSHALE":   ["vsh", "vshale", "shale volume", "clay volume"],
    "DEPTH_M":  ["top", "top_m", "formation top", "top depth"],
    "BASE_M":   ["base", "base_m", "bottom", "base depth"],
}


def _map_column(col_name: str) -> str:
    """Map an arbitrary column name to a canonical petrophysical mnemonic."""
    lower = col_name.lower().strip().replace(" ", "_").replace("-", "_")
    for canonical, synonyms in _COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if lower == syn or lower.startswith(syn):
                return canonical
    return col_name.upper()


# ── Regex-based data extraction ──────────────────────────────

_DEPTH_PATTERNS = [
    r"(?:top|from|at|depth)\s*[:\-=]?\s*(\d+\.?\d*)\s*m",
    r"(\d{3,5}\.?\d*)\s*(?:m|meters|mTVD|mMD)\b",
]

_FORMATION_PATTERNS = [
    r"(?:formation|zone|interval|member|unit)\s+['\"]?([A-Z][A-Za-z0-9\s\-]+?)['\"]?\s+(?:at|from|top)",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s+formation",
]

_FLOW_RATE_PATTERN = r"(\d+\.?\d*)\s*(?:bbl/d|bpd|b/d|STB/D)"
_GOR_PATTERN       = r"(?:GOR|gas.oil ratio)\s*[:\-=]?\s*(\d+\.?\d*)\s*(?:scf|mcf)/"

_POROSITY_PATTERN  = r"(?:porosity|phi|PHIE)\s*[:\-=]?\s*(\d+\.?\d*)\s*%?"
_PERM_PATTERN      = r"(?:permeability|k)\s*[:\-=]?\s*(\d+\.?\d*)\s*mD"
_API_PATTERN       = r"(\d{1,2}\.?\d*)\s*°?\s*API"


def _extract_numbers_with_context(text: str) -> Dict[str, Any]:
    """Extract key numerical values from free text."""
    values = {}

    # Flow rate
    m = re.search(_FLOW_RATE_PATTERN, text, re.IGNORECASE)
    if m:
        values["flow_rate_bpd"] = float(m.group(1))

    # GOR
    m = re.search(_GOR_PATTERN, text, re.IGNORECASE)
    if m:
        values["gor_scfbbl"] = float(m.group(1))

    # Porosity
    m = re.search(_POROSITY_PATTERN, text, re.IGNORECASE)
    if m:
        v = float(m.group(1))
        values["avg_porosity"] = v / 100 if v > 1 else v

    # Permeability
    m = re.search(_PERM_PATTERN, text, re.IGNORECASE)
    if m:
        values["avg_perm_mD"] = float(m.group(1))

    # API gravity
    m = re.search(_API_PATTERN, text, re.IGNORECASE)
    if m:
        values["api_gravity"] = float(m.group(1))

    return values


# ── Main class ───────────────────────────────────────────────

class DocumentIntelligence:
    """
    AI-powered document parser for petrophysical reports and data files.

    Combines:
    1. Rule-based text extraction (fast, always works)
    2. Gemini AI analysis (deep understanding, requires API key)

    Parameters
    ----------
    gemini_api_key : str, optional
        If provided, AI-enhanced extraction is enabled.
        Falls back to GEMINI_API_KEY environment variable.
    """

    def __init__(self, gemini_api_key: Optional[str] = None):
        import os
        self._api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self._ai_available = False
        self._ai = None

        if self._api_key:
            try:
                from project_QLE.ai.gemini_interpreter import GeminiInterpreter
                self._ai = GeminiInterpreter(api_key=self._api_key)
                self._ai_available = True
                logger.info("DocumentIntelligence: Gemini AI enabled")
            except Exception as e:
                logger.warning("DocumentIntelligence: Gemini not available (%s). Using rule-based extraction only.", e)

    # ── Public API ───────────────────────────────────────────

    def parse_pdf(self, path: str | Path) -> DocumentExtraction:
        """
        Extract structured petrophysical data from a PDF report.

        Handles: well completion reports, mudlogs, DST reports,
                 core analysis reports, petrophysical summaries.
        """
        path = Path(path)
        result = DocumentExtraction(source_file=str(path))

        # Step 1: Extract raw text
        try:
            import fitz
            doc = fitz.open(str(path))
            pages = [page.get_text() for page in doc]
            raw_text = "\n".join(pages)
            doc.close()
            result.raw_text = raw_text
        except ImportError:
            result.warnings.append("PyMuPDF not installed — cannot extract PDF text. pip install PyMuPDF")
            return result
        except Exception as e:
            result.warnings.append(f"PDF read error: {e}")
            return result

        # Step 2: Rule-based extraction
        result.key_values = _extract_numbers_with_context(raw_text)
        result.well_names = self._extract_well_names(raw_text)
        result.formation_tops = self._extract_formation_tops_from_text(raw_text)

        # Step 3: AI-enhanced extraction
        if self._ai_available:
            self._ai_extract_pdf(result)
        else:
            result.ai_summary = (
                "AI extraction not available (no Gemini API key). "
                "Rule-based extraction was used. Set GEMINI_API_KEY for deeper analysis."
            )

        return result

    def parse_csv(self, path: str | Path = None,
                  dataframe: pd.DataFrame = None) -> DocumentExtraction:
        """
        Intelligently parse a CSV / Excel file with unknown column layouts.

        Automatically maps arbitrary column names to canonical petrophysical
        mnemonics (DEPTH, GR, RHOB, PHIE, SW, etc.) and returns a clean
        DataFrame ready for petrophysical analysis.

        Parameters
        ----------
        path : str or Path, optional
            Path to a .csv or .xlsx file.
        dataframe : pd.DataFrame, optional
            Already-loaded DataFrame (for Streamlit uploaded files).
        """
        result = DocumentExtraction(source_file=str(path) if path else "uploaded_dataframe")

        # Load the data
        if dataframe is not None:
            df_raw = dataframe.copy()
        elif path is not None:
            path = Path(path)
            try:
                if path.suffix.lower() in (".xlsx", ".xls"):
                    df_raw = pd.read_excel(str(path))
                else:
                    df_raw = pd.read_csv(str(path))
            except Exception as e:
                result.warnings.append(f"CSV read error: {e}")
                return result
        else:
            result.warnings.append("Provide either path= or dataframe=")
            return result

        # Step 1: Numeric conversion
        df_raw = df_raw.apply(pd.to_numeric, errors="ignore")

        # Step 2: Column mapping
        column_map = {col: _map_column(col) for col in df_raw.columns}
        df_mapped  = df_raw.rename(columns=column_map)

        # Step 3: Deduplicate mapped column names
        seen: Dict[str, int] = {}
        new_cols = []
        for c in df_mapped.columns:
            if c in seen:
                seen[c] += 1
                new_cols.append(f"{c}_{seen[c]}")
            else:
                seen[c] = 0
                new_cols.append(c)
        df_mapped.columns = new_cols

        result.petro_dataframe = df_mapped
        result.document_type = self._classify_csv(df_mapped)

        # Step 4: Extract formation top table if detected
        if result.document_type == "formation_tops":
            result.formation_tops = self._csv_to_formation_tops(df_mapped)

        # Step 5: Extract DST data if detected
        elif result.document_type == "dst_data":
            result.dst_tests = self._csv_to_dst_tests(df_mapped)

        # Step 6: Summary statistics for petrophysical data
        if result.document_type == "petrophysical_log":
            result.key_values = {
                col: float(df_mapped[col].mean())
                for col in ["DEPTH", "GR", "RHOB", "NPHI", "PHIE", "SW", "PERM_mD"]
                if col in df_mapped.columns and df_mapped[col].notna().any()
            }

        # Step 7: AI description
        if self._ai_available:
            self._ai_describe_csv(result, df_raw)
        else:
            cols_found = list(df_mapped.columns)
            result.ai_summary = (
                f"CSV loaded with {len(df_mapped)} rows × {len(df_mapped.columns)} columns.\n"
                f"Detected type: {result.document_type}\n"
                f"Mapped columns: {', '.join(cols_found[:10])}"
                + (" …" if len(cols_found) > 10 else "")
            )

        return result

    def parse_text(self, text: str, source_name: str = "pasted_text") -> DocumentExtraction:
        """
        Extract petrophysical data from raw text (e.g., copy-pasted from a report).
        """
        result = DocumentExtraction(source_file=source_name, raw_text=text)
        result.key_values   = _extract_numbers_with_context(text)
        result.well_names   = self._extract_well_names(text)
        result.formation_tops = self._extract_formation_tops_from_text(text)

        if self._ai_available:
            self._ai_extract_pdf(result)

        return result

    # ── Internal: rule-based extraction ─────────────────────

    def _extract_well_names(self, text: str) -> List[str]:
        """Heuristic well name extraction."""
        patterns = [
            r"\bWell\s+([A-Z][A-Z0-9\-_]+)",
            r"\b([A-Z]{2,5}-\d+[A-Z]?)\b",             # e.g. NC-7A, QD-1
            r"\b(SIRTE|WAHA|INTISAR|SARIR)-?\d*\b",
        ]
        names = set()
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                name = m.group(1).strip().upper()
                if len(name) >= 3 and not name.isdigit():
                    names.add(name)
        return sorted(names)[:10]

    def _extract_formation_tops_from_text(self, text: str) -> List[Dict]:
        """Extract formation top depths from report text."""
        tops = []
        # Pattern: "Formation Name  2150 m" or "Intisar C: top at 2150"
        pattern = r"([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*)\s*(?:top|formation|zone)?\s*[:\-at]*\s*(\d{3,5}\.?\d*)\s*m"
        for m in re.finditer(pattern, text, re.IGNORECASE):
            formation_name = m.group(1).strip()
            depth = float(m.group(2))
            if 100 <= depth <= 8000:   # sanity: 100–8000 m is reasonable
                tops.append({
                    "formation_name": formation_name,
                    "depth_m": depth,
                    "base_m": depth + 50,   # estimate; AI will refine
                    "lithology": "Unknown",
                    "description": f"Auto-extracted from document text at {depth:.0f} m",
                })
        # Deduplicate by depth
        seen_depths = set()
        unique_tops = []
        for t in tops:
            if t["depth_m"] not in seen_depths:
                seen_depths.add(t["depth_m"])
                unique_tops.append(t)
        return unique_tops[:20]

    def _classify_csv(self, df: pd.DataFrame) -> str:
        """Determine what kind of data a CSV contains."""
        cols_lower = [c.lower() for c in df.columns]

        if any(c in cols_lower for c in ["gr", "rhob", "nphi", "phie", "depth"]):
            return "petrophysical_log"
        if any(c in cols_lower for c in ["formation_name", "top_m", "lithology", "depth_m"]):
            return "formation_tops"
        if any(c in cols_lower for c in ["flow_rate_bpd", "gor_scfbbl", "initial_shut_in_psi"]):
            return "dst_data"
        if any(c in cols_lower for c in ["perm", "porosity", "permeability"]):
            return "core_data"
        return "general_data"

    def _csv_to_formation_tops(self, df: pd.DataFrame) -> List[Dict]:
        """Convert a mapped formation tops DataFrame to list of dicts."""
        tops = []
        name_col  = next((c for c in df.columns if "NAME" in c.upper() or "FORMATION" in c.upper()), None)
        depth_col = next((c for c in df.columns if "TOP" in c.upper() or "DEPTH" in c.upper()), None)
        base_col  = next((c for c in df.columns if "BASE" in c.upper() or "BOTTOM" in c.upper()), None)
        litho_col = next((c for c in df.columns if "LITH" in c.upper()), None)

        if name_col and depth_col:
            for _, row in df.iterrows():
                top  = {
                    "formation_name": str(row.get(name_col, "Unknown")),
                    "depth_m":  float(row.get(depth_col, 0)),
                    "base_m":   float(row.get(base_col, row.get(depth_col, 0) + 50)) if base_col else float(row.get(depth_col, 0)) + 50,
                    "lithology": str(row.get(litho_col, "Unknown")) if litho_col else "Unknown",
                    "description": "Imported from CSV",
                }
                tops.append(top)
        return tops

    def _csv_to_dst_tests(self, df: pd.DataFrame) -> List[Dict]:
        """Convert a mapped DST DataFrame to list of dicts."""
        tests = []
        for _, row in df.iterrows():
            test = {}
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    test[col.lower()] = val
            if test:
                tests.append(test)
        return tests

    # ── Internal: AI extraction ──────────────────────────────

    def _ai_extract_pdf(self, result: DocumentExtraction):
        """Use Gemini to deeply analyse a PDF's text."""
        if not result.raw_text:
            return

        # Truncate to fit context
        text_sample = result.raw_text[:6000]

        prompt = f"""
You are a senior petroleum geologist at Waha Oil Company, Libya.
Analyse the following document text extracted from a well report and extract structured data.

DOCUMENT TEXT (first 6000 characters):
{text_sample}

Return a structured analysis covering:

1. DOCUMENT TYPE: (well completion report / DST report / mudlog / core report / petrophysical report / other)

2. WELL IDENTITY:
   - Well name(s)
   - Field name
   - Basin (Sirte / Ghadames / Murzuq / Offshore)
   - Company / operator

3. FORMATION TOPS (list all mentioned):
   Format: Formation name | Top depth (m) | Base depth (m) | Lithology
   Example: Intisar C | 2150 | 2210 | Limestone

4. DST RESULTS (if any):
   Format: Test name | Depth (m) | Fluid type | Flow rate (bpd) | Reservoir pressure (psi) | Permeability (mD) | Skin

5. KEY PETROPHYSICAL VALUES:
   - Average porosity (fraction or %)
   - Average permeability (mD)
   - Average water saturation (fraction or %)
   - Net pay (m)
   - OWC / GOC depth (m)
   - API gravity (°)

6. EXPLORATION RISK: LOW / MODERATE / HIGH (with one-sentence justification)

7. ONE-PARAGRAPH SUMMARY of the document's key findings.

Be concise and structured. Use N/A for missing information.
"""
        try:
            response = self._ai._call(prompt, max_tokens=1200)
            result.ai_summary = response

            # Parse formation tops from AI response
            ai_tops = self._parse_ai_formation_tops(response)
            if ai_tops:
                # Merge: AI tops override rule-based if same name exists
                existing_names = {t["formation_name"].lower() for t in result.formation_tops}
                for top in ai_tops:
                    if top["formation_name"].lower() not in existing_names:
                        result.formation_tops.append(top)

            # Parse document type
            if "completion report" in response.lower():
                result.document_type = "well_completion_report"
            elif "dst" in response.lower() or "drill stem" in response.lower():
                result.document_type = "dst_report"
            elif "mudlog" in response.lower() or "mud log" in response.lower():
                result.document_type = "mudlog"
            elif "core" in response.lower():
                result.document_type = "core_report"
            elif "petrophysical" in response.lower():
                result.document_type = "petrophysical_report"

            # Parse key values from AI text
            ai_values = _extract_numbers_with_context(response)
            result.key_values.update(ai_values)

        except Exception as e:
            result.warnings.append(f"AI extraction failed: {e}")

    def _ai_describe_csv(self, result: DocumentExtraction, df_raw: pd.DataFrame):
        """Use Gemini to interpret a CSV file's content and column meanings."""
        col_sample = df_raw.head(5).to_string(max_cols=15, max_rows=5)

        prompt = f"""
You are a petroleum data analyst at Waha Oil Company, Libya.
Analyse this CSV data sample and describe what it contains.

COLUMNS: {list(df_raw.columns)}
SAMPLE DATA:
{col_sample}

Provide:
1. DATASET TYPE: (petrophysical log / formation tops / DST data / core analysis / production data / other)
2. COLUMN MAPPING: Map each column to a standard petrophysical mnemonic if applicable
   Example: "depth_m → DEPTH, gamma_ray → GR, phi_total → PHIE"
3. DATA QUALITY: Note any issues (missing values, unusual units, suspect ranges)
4. RECOMMENDED USE: How should this data be used in the Project_QLE platform?
5. ONE-LINE SUMMARY of what this dataset represents.
"""
        try:
            response = self._ai._call(prompt, max_tokens=600)
            result.ai_summary = response
        except Exception as e:
            result.warnings.append(f"AI description failed: {e}")
            result.ai_summary = f"CSV with {len(df_raw)} rows loaded. AI description unavailable."

    def _parse_ai_formation_tops(self, ai_text: str) -> List[Dict]:
        """Parse formation tops out of AI response text."""
        tops = []
        # Look for "Name | depth | base | lithology" pattern in AI output
        pattern = r"([A-Za-z][A-Za-z0-9\s\-]+?)\s*\|\s*(\d+\.?\d*)\s*\|\s*(\d+\.?\d*)\s*\|\s*([A-Za-z]+)"
        for m in re.finditer(pattern, ai_text):
            name  = m.group(1).strip()
            top   = float(m.group(2))
            base  = float(m.group(3))
            litho = m.group(4).strip()
            if 50 <= top <= 8000 and base >= top:
                tops.append({
                    "formation_name": name,
                    "depth_m": top,
                    "base_m":  base,
                    "lithology": litho,
                    "description": f"AI-extracted from document. Top: {top:.0f} m, Base: {base:.0f} m.",
                })
        return tops


# ── Convenience function ─────────────────────────────────────

def analyse_uploaded_file(file_bytes: bytes, filename: str,
                           gemini_api_key: Optional[str] = None) -> DocumentExtraction:
    """
    One-call function for use in the Streamlit app.

    Accepts a file's bytes and filename, detects format, and returns extraction.
    """
    intel = DocumentIntelligence(gemini_api_key=gemini_api_key)
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        # Write to temp file
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            return intel.parse_pdf(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    elif suffix in (".csv", ".txt"):
        import io
        df = pd.read_csv(io.StringIO(file_bytes.decode("utf-8", errors="replace")))
        return intel.parse_csv(dataframe=df)

    elif suffix in (".xlsx", ".xls"):
        import io
        df = pd.read_excel(io.BytesIO(file_bytes))
        return intel.parse_csv(dataframe=df)

    else:
        result = DocumentExtraction(source_file=filename)
        result.warnings.append(f"Unsupported format: {suffix}")
        return result