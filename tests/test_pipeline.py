"""
Project_QLE/tests/test_pipeline.py
─────────────────────────────
Unit + integration tests using synthetic well-log data.
No real files required – everything is generated in-memory.

Run with:
    python -m pytest Project_QLE/tests/ -v
or simply:
    python Project_QLE/tests/test_pipeline.py
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import io
import tempfile
import unittest

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
#  Synthetic data factories
# ─────────────────────────────────────────────

def make_synthetic_las(
    well_name: str = "SYNTHETIC-1",
    n_samples: int = 500,
    start: float = 2000.0,
    step: float  = 0.5,
) -> "lasio.LASFile":
    """Build a minimal lasio.LASFile in memory."""
    import lasio

    depth = np.arange(start, start + n_samples * step, step)[:n_samples]
    rng   = np.random.default_rng(42)

    # Simulate alternating sand / shale layers
    gr   = np.where((depth % 50) < 25, rng.normal(30, 5, n_samples), rng.normal(100, 10, n_samples))
    rhob = np.where(gr < 60, rng.normal(2.35, 0.05, n_samples), rng.normal(2.55, 0.05, n_samples))
    nphi = np.where(gr < 60, rng.normal(0.25, 0.03, n_samples), rng.normal(0.10, 0.02, n_samples))
    rt   = np.where(gr < 60, rng.lognormal(2.0, 0.5, n_samples), rng.lognormal(0.5, 0.3, n_samples))
    dt   = rng.normal(80, 5, n_samples)

    las = lasio.LASFile()
    las.well.WELL = lasio.HeaderItem("WELL", value=well_name)
    las.well.STRT = lasio.HeaderItem("STRT", value=depth[0],  unit="M")
    las.well.STOP = lasio.HeaderItem("STOP", value=depth[-1], unit="M")
    las.well.STEP = lasio.HeaderItem("STEP", value=step,      unit="M")
    las.well.NULL = lasio.HeaderItem("NULL", value=-999.25)

    las.append_curve("DEPT", depth, unit="M",     descr="Depth")
    las.append_curve("GR",   gr,    unit="GAPI",  descr="Gamma Ray")
    las.append_curve("RHOB", rhob,  unit="G/C3",  descr="Bulk Density")
    las.append_curve("NPHI", nphi,  unit="V/V",   descr="Neutron Porosity")
    las.append_curve("RT",   rt,    unit="OHMM",  descr="True Resistivity")
    las.append_curve("DT",   dt,    unit="US/F",  descr="Sonic")

    return las


def write_las_tempfile(las) -> str:
    """Write a lasio.LASFile to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".las", delete=False)
    las.write(tmp.name)
    return tmp.name


# ─────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────

class TestModels(unittest.TestCase):
    def test_well_header(self):
        from geoProject_QLEai.core.models import WellHeader
        h = WellHeader(well_name="TEST-1", latitude=25.0, longitude=56.0)
        self.assertEqual(h.well_name, "TEST-1")
        self.assertAlmostEqual(h.latitude, 25.0)

    def test_zone_interval(self):
        from Project_QLE.core.models import ZoneInterval, Facies, FluidType
        z = ZoneInterval(top=2000, base=2050, facies=Facies.SANDSTONE, fluid=FluidType.OIL)
        self.assertEqual(z.facies, Facies.SANDSTONE)


class TestLASParser(unittest.TestCase):
    def setUp(self):
        import lasio
        las = make_synthetic_las("TEST-LAS")
        self.las_path = write_las_tempfile(las)

    def test_parse_las(self):
        from Project_QLE.parsers import parse_las
        well = parse_las(self.las_path)
        self.assertEqual(well.header.well_name, "TEST-LAS")
        self.assertIn("GR", well.curves)
        self.assertIn("RHOB", well.curves)
        self.assertGreater(len(well.curves["GR"].data), 0)

    def test_depth_array(self):
        from Project_QLE.parsers import parse_las
        well = parse_las(self.las_path)
        depth = well.get_depth()
        self.assertIsNotNone(depth)
        self.assertGreater(len(depth), 0)


class TestPetrophysics(unittest.TestCase):
    def setUp(self):
        import lasio
        las = make_synthetic_las("PETRO-WELL")
        path = write_las_tempfile(las)
        from Project_QLE.parsers import parse_las
        self.well = parse_las(path)

    def test_engine_run(self):
        from Project_QLE.analysis import PetrophysicsEngine
        engine = PetrophysicsEngine(self.well)
        df = engine.run()
        self.assertIn("VSHALE", df.columns)
        self.assertIn("PHIE",   df.columns)
        self.assertIn("SW",     df.columns)
        self.assertIn("PERM_mD", df.columns)

    def test_vshale_range(self):
        from Project_QLE.analysis import PetrophysicsEngine
        df = PetrophysicsEngine(self.well).run()
        vsh = df["VSHALE"].dropna()
        self.assertTrue((vsh >= 0).all() and (vsh <= 1).all(),
                        f"Vshale out of range: min={vsh.min():.3f}, max={vsh.max():.3f}")

    def test_porosity_range(self):
        from Project_QLE.analysis import PetrophysicsEngine
        df = PetrophysicsEngine(self.well).run()
        phi = df["PHIE"].dropna()
        self.assertTrue((phi >= 0).all() and (phi <= 1).all())


class TestFacies(unittest.TestCase):
    def setUp(self):
        import lasio
        las = make_synthetic_las("FACIES-WELL")
        path = write_las_tempfile(las)
        from Project_QLE.parsers import parse_las
        from Project_QLE.analysis import PetrophysicsEngine
        well = parse_las(path)
        self.df = PetrophysicsEngine(well).run()
        self.well = well

    def test_rule_based(self):
        from Project_QLE.analysis import RuleBasedFacies
        clf = RuleBasedFacies()
        labels = clf.classify(self.df)
        self.assertEqual(len(labels), len(self.df))
        unique = set(labels)
        self.assertTrue(len(unique) >= 2, f"Expected ≥2 facies classes, got: {unique}")

    def test_kmeans(self):
        from Project_QLE.analysis import KMeansFacies
        clf = KMeansFacies(n_clusters=3)
        labels = clf.fit_predict(self.df)
        self.assertEqual(len(labels), len(self.df))

    def test_labels_to_zones(self):
        from Project_QLE.analysis import RuleBasedFacies, labels_to_zones
        clf = RuleBasedFacies()
        labels = clf.classify(self.df)
        depth  = self.well.get_depth()
        zones  = labels_to_zones(depth, labels)
        self.assertGreater(len(zones), 0)


class TestStatistics(unittest.TestCase):
    def setUp(self):
        import lasio
        las = make_synthetic_las("STATS-WELL")
        path = write_las_tempfile(las)
        from Project_QLE.parsers import parse_las
        self.well = parse_las(path)

    def test_descriptive_stats(self):
        from Project_QLE.analysis import descriptive_stats
        result = descriptive_stats(self.well, "GR")
        self.assertGreater(result.n, 0)
        self.assertGreater(result.std, 0)
        self.assertLessEqual(result.p10, result.p50)
        self.assertLessEqual(result.p50, result.p90)

    def test_batch_stats(self):
        from Project_QLE.analysis import batch_stats
        results = batch_stats(self.well)
        self.assertGreater(len(results), 0)


class TestCorrelation(unittest.TestCase):
    def test_two_well_correlation(self):
        import lasio
        from Project_QLE.parsers import parse_las
        from Project_QLE.analysis import correlate_wells

        path_a = write_las_tempfile(make_synthetic_las("WELL-A", start=2000))
        path_b = write_las_tempfile(make_synthetic_las("WELL-B", start=2000))
        wa = parse_las(path_a)
        wb = parse_las(path_b)
        result = correlate_wells(wa, wb, curve="GR")
        self.assertIsNotNone(result.pearson_r)
        self.assertTrue(-1 <= result.pearson_r <= 1)


class TestReservoir(unittest.TestCase):
    def test_build_summary(self):
        import lasio
        from Project_QLE.parsers import parse_las
        from Project_QLE.analysis import PetrophysicsEngine, RuleBasedFacies, labels_to_zones, build_reservoir_summary

        path = write_las_tempfile(make_synthetic_las("RES-WELL"))
        well = parse_las(path)
        df   = PetrophysicsEngine(well).run()
        labels = RuleBasedFacies().classify(df)
        zones  = labels_to_zones(well.get_depth(), labels)
        rs = build_reservoir_summary(well, df, zones)
        self.assertEqual(rs.well_name, "RES-WELL")
        self.assertIsNotNone(rs.net_pay_m)
        self.assertGreaterEqual(rs.net_pay_m, 0)


# ─────────────────────────────────────────────
#  Demo run (no pytest needed)
# ─────────────────────────────────────────────

def demo_run():
    """Quick end-to-end demo without real files or AI key."""
    print("\n" + "="*60)
    print("  Project_QLE Platform – Synthetic Demo Run")
    print("="*60 + "\n")

    import lasio
    from Project_QLE.parsers  import parse_las
    from Project_QLE.analysis import (
        PetrophysicsEngine, KMeansFacies, labels_to_zones,
        batch_stats, correlate_wells, build_reservoir_summary,
    )

    # Create two synthetic wells
    wells = []
    for i, (name, lat, lon, start) in enumerate([
        ("DEMO-WELL-1", 28.5, 55.2, 2000),
        ("DEMO-WELL-2", 28.6, 55.3, 2050),
    ]):
        las = make_synthetic_las(name, start=start)
        las.well["LATI"] = lasio.HeaderItem("LATI", value=lat)
        las.well["LONG"] = lasio.HeaderItem("LONG", value=lon)
        path = write_las_tempfile(las)
        well = parse_las(path)
        wells.append(well)
        print(f"  ✓ {name}: {len(well.curves)} curves, "
              f"depth {well.header.start_depth:.0f}–{well.header.stop_depth:.0f} m")

    print("\n--- Petrophysics ---")
    dfs = {}
    for w in wells:
        df = PetrophysicsEngine(w).run()
        dfs[w.header.well_name] = df
        w.df = df
        print(f"  {w.header.well_name}: PHIE mean={df['PHIE'].mean():.3f}, "
              f"Sw mean={df['SW'].mean():.3f}")

    print("\n--- Facies (KMeans) ---")
    clf = KMeansFacies(n_clusters=4)
    for w in wells:
        labels = clf.fit_predict(dfs[w.header.well_name])
        dfs[w.header.well_name]["FACIES"] = labels
        print(f"  {w.header.well_name}: {dict(zip(*np.unique(labels, return_counts=True)))}")

    print("\n--- Statistics ---")
    from Project_QLE.analysis import descriptive_stats
    stat = descriptive_stats(wells[0], "GR")
    print(f"  GR ({wells[0].header.well_name}): mean={stat.mean:.1f} std={stat.std:.1f} "
          f"P10={stat.p10:.1f} P90={stat.p90:.1f}")

    print("\n--- Cross-well Correlation ---")
    result = correlate_wells(wells[0], wells[1], "GR")
    print(f"  {result.well_a} vs {result.well_b}: r={result.pearson_r:.3f}, lag={result.lag_m:.1f} m")

    print("\n--- Reservoir Summaries ---")
    for w in wells:
        df = dfs[w.header.well_name]
        labels = df["FACIES"].values
        zones  = labels_to_zones(w.get_depth(), labels)
        rs = build_reservoir_summary(w, df, zones)
        print(f"  {w.header.well_name}: net_pay={rs.net_pay_m:.1f} m, "
              f"φ={rs.avg_porosity:.3f}, Sw={rs.avg_sw:.3f}, "
              f"k={rs.avg_perm_mD:.1f} mD, "
              f"OWC={rs.fluid_contact:.1f} m" if rs.fluid_contact else "  OWC not detected")

    print("\n" + "="*60)
    print("  Demo complete – all systems operational!")
    print("="*60 + "\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Run demo instead of tests")
    args = parser.parse_args()

    if args.demo:
        demo_run()
    else:
        unittest.main(argv=[__file__], verbosity=2)