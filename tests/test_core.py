"""
Project_QLE/tests/test_core.py
──────────────────────────────
Unit tests using synthetic Libya-calibrated well data.

Run:
    python -m pytest Project_QLE/tests/ -v
or:
    python Project_QLE/tests/test_core.py --demo
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import tempfile
import unittest
import numpy as np
import pandas as pd


# ─────────────────────────────────────────────
#  Synthetic LAS factory (Libya-calibrated)
# ─────────────────────────────────────────────

def make_sirte_las(well_name="SIRTE-TEST-1", n=400, start=2000.0):
    """Simulate a Sirte Basin carbonate well."""
    import lasio
    depth = np.arange(start, start + n * 0.5, 0.5)[:n]
    rng   = np.random.default_rng(7)
    # Alternating carbonate reservoir / shale intervals
    is_res = (depth % 60) < 35
    gr   = np.where(is_res, rng.normal(12, 3, n), rng.normal(85, 12, n))
    rhob = np.where(is_res, rng.normal(2.25, 0.06, n), rng.normal(2.60, 0.04, n))
    nphi = np.where(is_res, rng.normal(0.22, 0.03, n), rng.normal(0.09, 0.02, n))
    rt   = np.where(is_res, rng.lognormal(2.5, 0.6, n), rng.lognormal(0.5, 0.3, n))
    dt   = np.where(is_res, rng.normal(72, 4, n), rng.normal(55, 3, n))

    las = lasio.LASFile()
    las.well["WELL"] = lasio.HeaderItem("WELL", value=well_name)
    las.well["STRT"] = lasio.HeaderItem("STRT", value=depth[0],  unit="M")
    las.well["STOP"] = lasio.HeaderItem("STOP", value=depth[-1], unit="M")
    las.well["STEP"] = lasio.HeaderItem("STEP", value=0.5,       unit="M")
    las.well["NULL"] = lasio.HeaderItem("NULL", value=-999.25)
    las.well["LATI"] = lasio.HeaderItem("LATI", value=28.5)
    las.well["LONG"] = lasio.HeaderItem("LONG", value=21.2)
    for mnemonic, data, unit in [
        ("DEPT", depth, "M"), ("GR", gr, "GAPI"),
        ("RHOB", rhob, "G/C3"), ("NPHI", nphi, "V/V"),
        ("RT", rt, "OHMM"), ("DT", dt, "US/F"),
    ]:
        las.append_curve(mnemonic, data, unit=unit)
    tmp = tempfile.NamedTemporaryFile(suffix=".las", delete=False)
    las.write(tmp.name)
    return tmp.name


# ─────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────

class TestLibyaGeology(unittest.TestCase):
    def test_basin_defaults(self):
        from Project_QLE.core.libya_geology import get_basin_defaults
        for b in ["SIRTE","GHADAMES","MURZUQ"]:
            d = get_basin_defaults(b)
            self.assertIn("gr_clean", d)
            self.assertIn("rho_matrix", d)
            self.assertLess(d["gr_clean"], d["gr_shale"])

    def test_sirte_carbonate_matrix(self):
        from Project_QLE.core.libya_geology import get_basin_defaults
        d = get_basin_defaults("SIRTE")
        self.assertAlmostEqual(d["rho_matrix"], 2.71, places=2)

    def test_ghadames_clastic_matrix(self):
        from Project_QLE.core.libya_geology import get_basin_defaults
        d = get_basin_defaults("GHADAMES")
        self.assertAlmostEqual(d["rho_matrix"], 2.65, places=2)


class TestModels(unittest.TestCase):
    def test_well_header_basin(self):
        from Project_QLE.core.models import WellHeader
        h = WellHeader(well_name="SARIR-1", basin="SIRTE")
        self.assertEqual(h.basin, "SIRTE")

    def test_zone_interval(self):
        from Project_QLE.core.models import ZoneInterval, Facies, FluidType
        z = ZoneInterval(top=2100, base=2180, facies=Facies.LIMESTONE, fluid=FluidType.OIL)
        self.assertEqual(z.facies.value, "Limestone")
        self.assertEqual(z.fluid.value,  "Oil")


class TestPetrophysics(unittest.TestCase):
    def setUp(self):
        path = make_sirte_las("PETRO-1")
        from Project_QLE.parsers import parse_las
        self.well = parse_las(path)
        self.well.header.basin = "SIRTE"

    def test_engine_sirte(self):
        from Project_QLE.analysis import PetrophysicsEngine
        df = PetrophysicsEngine(self.well, basin="SIRTE").run()
        for col in ["VSHALE","PHIE","SW","PERM_mD","PORE_PRESS_PSI"]:
            self.assertIn(col, df.columns)

    def test_vshale_bounds(self):
        from Project_QLE.analysis import PetrophysicsEngine
        df = PetrophysicsEngine(self.well, basin="SIRTE").run()
        v  = df["VSHALE"].dropna()
        self.assertTrue((v >= 0).all() and (v <= 1).all())

    def test_sw_bounds(self):
        from Project_QLE.analysis import PetrophysicsEngine
        df = PetrophysicsEngine(self.well, basin="SIRTE").run()
        sw = df["SW"].dropna()
        self.assertTrue((sw >= 0).all() and (sw <= 1).all())

    def test_perm_positive(self):
        from Project_QLE.analysis import PetrophysicsEngine
        df = PetrophysicsEngine(self.well, basin="SIRTE").run()
        k  = df["PERM_mD"].dropna()
        self.assertTrue((k > 0).all())


class TestFacies(unittest.TestCase):
    def setUp(self):
        path = make_sirte_las("FACIES-1")
        from Project_QLE.parsers import parse_las
        from Project_QLE.analysis import PetrophysicsEngine
        self.well = parse_las(path)
        self.well.header.basin = "SIRTE"
        self.df = PetrophysicsEngine(self.well, basin="SIRTE").run()

    def test_rule_based(self):
        from Project_QLE.analysis import RuleBasedFacies
        labels = RuleBasedFacies().classify(self.df)
        self.assertEqual(len(labels), len(self.df))
        self.assertGreaterEqual(len(set(labels)), 2)

    def test_kmeans(self):
        from Project_QLE.analysis import KMeansFacies, labels_to_zones
        labels = KMeansFacies(n_clusters=4).fit_predict(self.df)
        zones  = labels_to_zones(self.well.get_depth(), labels)
        self.assertGreater(len(zones), 0)


class TestReservoir(unittest.TestCase):
    def test_summary(self):
        path = make_sirte_las("RES-1")
        from Project_QLE.parsers import parse_las
        from Project_QLE.analysis import PetrophysicsEngine, KMeansFacies, labels_to_zones, build_reservoir_summary
        well = parse_las(path)
        df   = PetrophysicsEngine(well, basin="SIRTE").run()
        labels = KMeansFacies(n_clusters=4).fit_predict(df)
        zones  = labels_to_zones(well.get_depth(), labels)
        rs = build_reservoir_summary(well, df, zones)
        self.assertIsNotNone(rs.net_pay_m)
        self.assertGreaterEqual(rs.net_pay_m, 0)


# ─────────────────────────────────────────────
#  Demo
# ─────────────────────────────────────────────

def demo():
    print("\n" + "="*60)
    print("  Project_QLE – Libya Calibrated Demo")
    print("="*60)

    from Project_QLE.parsers  import parse_las
    from Project_QLE.analysis import (PetrophysicsEngine, KMeansFacies,
                                       labels_to_zones, build_reservoir_summary,
                                       descriptive_stats, correlate_wells)
    from Project_QLE.core.libya_geology import get_basin_defaults, LIBYAN_BASINS

    paths = [make_sirte_las(f"SIRTE-{i}", start=2000+i*50) for i in range(1, 3)]
    wells = [parse_las(p) for p in paths]
    for w in wells:
        w.header.basin = "SIRTE"

    print(f"\nBasin: {LIBYAN_BASINS['SIRTE']}")
    cfg = get_basin_defaults("SIRTE")
    print(f"  GR clean={cfg['gr_clean']}, GR shale={cfg['gr_shale']}")
    print(f"  ρ matrix={cfg['rho_matrix']} g/cc (carbonate)")
    print(f"  Rw={cfg['rw']} ohm-m  |  OBG={cfg['overburden_gradient']} psi/ft")

    print("\n--- Petrophysics (Sirte Basin) ---")
    dfs = {}
    for w in wells:
        df = PetrophysicsEngine(w, basin="SIRTE").run()
        dfs[w.header.well_name] = df
        w.df = df
        print(f"  {w.header.well_name}: PHIE={df['PHIE'].mean():.3f}  "
              f"Sw={df['SW'].mean():.3f}  k={df['PERM_mD'].mean():.1f} mD")

    print("\n--- Facies ---")
    for w in wells:
        labels = KMeansFacies(n_clusters=4).fit_predict(dfs[w.header.well_name])
        unique, counts = np.unique(labels, return_counts=True)
        print(f"  {w.header.well_name}: {dict(zip(unique, counts))}")

    print("\n--- Reservoir Summary ---")
    for w in wells:
        df = dfs[w.header.well_name]
        labels = KMeansFacies(n_clusters=4).fit_predict(df)
        zones  = labels_to_zones(w.get_depth(), labels)
        rs = build_reservoir_summary(w, df, zones)
        owc = f"{rs.fluid_contact:.1f} m" if rs.fluid_contact else "Not detected"
        print(f"  {w.header.well_name}: net_pay={rs.net_pay_m:.1f} m  "
              f"φ={rs.avg_porosity:.3f}  Sw={rs.avg_sw:.3f}  OWC={owc}")

    print("\n--- Cross-well Correlation ---")
    result = correlate_wells(wells[0], wells[1], "GR")
    print(f"  GR correlation: r={result.pearson_r:.3f}  lag={result.lag_m:.1f} m")

    print("\n" + "="*60)
    print("  ✓ All systems operational. Run: streamlit run Project_QLE/app.py")
    print("="*60 + "\n")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    args = p.parse_args()
    if args.demo:
        demo()
    else:
        unittest.main(argv=[__file__], verbosity=2)