# Project_QLE – Oil Exploration Interpretation Platform

> **Phase 1 — Backend Core** (prototype Streamlit dashboard included)  
> AI-assisted well-log interpretation with both Claude and Gemini support
## Project_QLE/README.md
---

## Architecture

```
Project_QLE/
├── core/
│   ├── models.py           ← Pydantic data models (WellLog, ReservoirSummary, …)
│   └── libya_geology.py    ← Basin defaults & Libyan field metadata
│
├── parsers/
│   ├── file_parser.py      ← PDF, DOCX, XML, JPG, CSV
│   ├── las_parser.py       ← LAS 1.2 / 2.0 / 3.0 well logs
│   └── segy_parser.py      ← SEG-Y seismic files
│
├── analysis/
│   ├── petrophysics.py     ← Vshale, porosity (ρ/N/sonic), Sw (Archie/Simandoux), pressure, perm
│   ├── facies.py           ← Rule-based, KMeans, Random Forest, MLP classifiers
│   ├── statistics.py       ← Descriptive stats, normality tests, outlier detection, MC uncertainty
│   ├── log_correlation.py  ← Cross-well Pearson/DTW, formation top picking, marker correlation
│   └── reservoir.py        ← Net pay, fluid contacts, FZI, Lorenz, STOIIP/GIIP
│
├── ai/
│   ├── interpreter.py      ← Anthropic Claude API: reservoir narrative, Q&A, anomaly explanation
│   ├── gemini_interpreter.py ← Google Gemini API: Libya-calibrated geological interpretation
│   └── map_generator.py    ← Interpolated property maps, isopach, structure contours
│
├── app.py                  ← Streamlit dashboard (interactive UI)
├── pipeline.py             ← End-to-end orchestration pipeline
├── requirements.txt        ← Dependencies (pip install -r requirements.txt)
└── tests/
    ├── test_core.py        ← Unit tests with Libya-calibrated synthetic wells
    └── test_pipeline.py    ← Integration tests (run with --demo flag)
```

---

## Quick Start

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Run the synthetic demo (no real files needed)

```bash
python Project_QLE/tests/test_pipeline.py --demo
```

### 3. Run unit tests

```bash
python -m pytest Project_QLE/tests/ -v
```

### 4. Run the Streamlit dashboard

```bash
streamlit run app.py
```

### 5. Use the pipeline with your own data

```python
import os
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-..."

from Project_QLE.pipeline import GeoAIPipeline

pipe = GeoAIPipeline(project_name="Block-7 Exploration", use_ai=True)

# Add LAS well logs
pipe.add_las("data/WELL-A.las")
pipe.add_las("data/WELL-B.las")
pipe.add_las("data/WELL-C.las")

# Add supporting documents (PDF reports, CSV tables …)
pipe.add_file("data/mudlog_report.pdf")
pipe.add_file("data/pressure_data.csv")

# Run the full interpretation
report = pipe.run()

# Access results
print(report.ai_summary)
for rs in report.reservoirs:
    print(f"\n{rs.well_name}: net_pay={rs.net_pay_m:.1f} m")
    print(rs.ai_narrative)
```

### 5. Low-level API (individual modules)

```python
from Project_QLE.parsers          import parse_las
from Project_QLE.analysis         import PetrophysicsEngine, KMeansFacies, labels_to_zones
from Project_QLE.analysis         import descriptive_stats, correlate_wells
from Project_QLE.analysis         import build_reservoir_summary
from Project_QLE.ai               import AIInterpreter, GeminiInterpreter
from Project_QLE.ai.map_generator import property_map, isopach_map

# Parse a LAS file
well = parse_las("WELL-A.las")

# Run petrophysics
df = PetrophysicsEngine(well).run()

# Classify facies
clf    = KMeansFacies(n_clusters=5)
labels = clf.fit_predict(df)
zones  = labels_to_zones(well.get_depth(), labels)

# Reservoir summary
rs = build_reservoir_summary(well, df, zones)
print(f"Net pay: {rs.net_pay_m:.1f} m, OWC: {rs.fluid_contact}")

# AI narrative
ai = AIInterpreter()
print(ai.interpret_reservoir(rs))

# Generate a porosity map (needs ≥3 wells with lat/lon)
fig = property_map([well], [rs], prop="avg_porosity", save_path="phi_map.png")
```

---

## Supported File Formats

| Format | Parser         | Notes                          |
|--------|---------------|--------------------------------|
| `.las` | lasio          | LAS 1.2, 2.0, 3.0              |
| `.segy`/`.sgy` | segyio | 2-D and 3-D SEG-Y            |
| `.pdf` | PyMuPDF        | Text extraction + images       |
| `.docx`| python-docx    | Paragraphs + tables            |
| `.xml` | lxml           | Auto-flattened to DataFrame    |
| `.jpg`/`.png` | Pillow  | Metadata + raw bytes           |
| `.csv` | pandas         | Auto numeric inference         |

---

## Key Analysis Capabilities

### Petrophysics
- **Vshale** – Larionov (old/young), Clavier, Stieber, SP methods
- **Porosity** – Density (PHID), Neutron-Density crossplot (PHIND), Sonic Wyllie / Raymer
- **Water Saturation** – Archie (clean sands), Simandoux (shaly sands), Indonesia
- **Pore Pressure** – Eaton's sonic method
- **Permeability** – Timur, Coates correlations

### Facies Classification
- Rule-based (GR + RHOB + NPHI thresholds)
- Unsupervised KMeans clustering
- Supervised Random Forest (with labelled training data)
- MLP Neural Network

### Statistics
- Full descriptive stats with P10/P50/P90
- Normality tests (Shapiro-Wilk, K-S, D'Agostino)
- Outlier detection (IQR, Z-score, Isolation Forest)
- Cross-correlation between log curves
- Monte Carlo porosity uncertainty

### Log Correlation
- Pearson + DTW similarity between wells
- Formation top auto-picking from GR gradient
- Multi-well marker correlation table

### Reservoir Characterization
- Net pay with cut-off filters (φ, Sw, Vsh, k)
- Fluid contact (OWC/GOC) detection
- Flow zone indicator (FZI) + Lorenz coefficient
- STOIIP / GIIP volumetric estimation

### AI Interpretation (Claude / Gemini)
- Reservoir narrative reports
- Cross-well correlation commentary
- Anomaly explanation
- Executive project summary
- Free-form geological Q&A

---

## Phase 2 (Coming) – Streamlit Dashboard

The Streamlit UI will add:
- Interactive well log viewer (track-by-track)
- Drag-and-drop file upload
- Interactive maps (Plotly)
- AI chat interface for geological Q&A
- Report export (PDF / Excel)