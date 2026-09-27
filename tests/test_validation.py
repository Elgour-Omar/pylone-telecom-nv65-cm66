"""Checks the Python tool against values printed by Robot Structural Analysis.

    python -m unittest discover tests      (from the repository root)
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pylon import cm66, nv65  # noqa: E402
from pylon.robot_io import load, robot_axial, robot_nodal_loads  # noqa: E402

DATA = ROOT / "data"
SECTIONS = [("T1", 0.0, 20.0), ("T2", 20.0, 25.0)]


class BucklingCoefficient(unittest.TestCase):
    """k0 printed in Robot's CM66 (Additif 80) member notes."""

    def test_k0_matches_robot_notes(self):
        for slenderness, robot_k0 in ((174.06, 4.48), (89.35, 1.76), (331.13, 14.18), (169.66, 4.29), (175.56, 4.54)):
            self.assertAlmostEqual(cm66.k0(slenderness), robot_k0, delta=0.01)


class WindNV65(unittest.TestCase):
    """Outline areas and section forces against Robot's NV65 wind note (saved model)."""

    @classmethod
    def setUpClass(cls):
        cls.model, _, _ = load(DATA / "robot_model_saved.json", DATA / "robot_loads_saved.json", state="saved")
        cls.sections = {s["section"]: s for s in nv65.section_forces(cls.model, SECTIONS, nv65.WindInput())}

    def test_outline_areas(self):
        self.assertAlmostEqual(self.sections["T1"]["S"], 60.0, places=6)
        self.assertAlmostEqual(self.sections["T2"]["S"], 5.0, places=6)

    def test_height_factor(self):
        self.assertAlmostEqual(nv65.height_factor(20.0), 1.188, places=3)
        self.assertAlmostEqual(nv65.height_factor(25.0), 1.265, places=3)

    def test_section_forces_within_6_percent(self):
        # Robot measures the exposed width of inclined bars slightly differently (Sp 9.28 vs 8.80 m2 for T1),
        # which gives a systematic gap of about 5 %.
        robot_daN = {"T1": (1239.76, 1361.68), "T2": (189.44, 222.96)}
        for name, (normal, diagonal) in robot_daN.items():
            s = self.sections[name]
            self.assertLess(abs(s["T_normal"] / 10 / normal - 1), 0.06, name)
            self.assertLess(abs(s["T_diag"] / 10 / diagonal - 1), 0.06, name)


class FrameSolver(unittest.TestCase):
    """Same loads as Robot -> same maximum compression per family."""

    def test_max_compression_within_2_percent(self):
        # 2 % or 0.1 kN, whichever is larger (diagonals carry only ~0.7 kN under self weight)
        model, m, ld = load(DATA / "robot_model_rapport.json", DATA / "robot_loads_rapport.json", state="report")
        K = model.stiffness()
        for case, F in ((1, model.self_weight()), (4, robot_nodal_loads(model, ld, 4)), (5, robot_nodal_loads(model, ld, 5))):
            forces = model.bar_end_forces(model.solve(F, K))
            robot = robot_axial(m, case)
            for fam in ("chord", "diagonal"):
                bars = [b.n for b in model.bars if b.family == fam]
                py = min(model.axial(forces[b]) for b in bars)
                rb = min(robot[b] for b in bars)
                self.assertLess(abs(py - rb), max(0.02 * abs(rb), 100.0), f"case {case} {fam}")


if __name__ == "__main__":
    unittest.main()
