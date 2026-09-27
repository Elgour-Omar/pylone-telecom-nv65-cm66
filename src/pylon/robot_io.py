"""Build a Model from the JSON files written by robot_extract*.py."""
import json
from pathlib import Path

import numpy as np

from .frame3d import Bar, Model, Section

FAMILY_BY_STATE = {
    "saved": {"CAEP 90x12": "chord", "CAEP 60x8": "diagonal", "CAEP 30x5": "secondary"},
    "report": {"CAEP 60x8": "chord", "CAEP 50x6": "diagonal", "CAEP 25x3": "secondary"},
}


def load(model_json, loads_json, pinned_families=(), state="saved"):
    FAMILY = FAMILY_BY_STATE[state]
    m = json.loads(Path(model_json).read_text(encoding="utf-8"))
    ld = json.loads(Path(loads_json).read_text(encoding="utf-8"))
    sections = {k: Section(k, v["AX"], v["IY"], v["IZ"], v["IX"], v["WY"], v["WZ"], v["D"])
                for k, v in ld["sections"].items()}
    used = {b["i"] for b in m["bars"]} | {b["j"] for b in m["bars"]}
    nodes = {n["n"]: (n["x"], n["y"], n["z"]) for n in m["nodes"] if n["n"] in used}  # drops stray nodes
    supports = {n["n"]: (True,) * 6 for n in m["nodes"] if n["support"]}
    bars = []
    for b in m["bars"]:
        fam = FAMILY.get(b["section"], b["section"])
        bars.append(Bar(b["n"], b["i"], b["j"], sections[b["section"]],
                        ld["bars"][str(b["n"])]["gamma"], fam in pinned_families, fam))
    mat = next(iter(ld["materials"].values()))
    model = Model(nodes, bars, supports, E=mat["E"], nu=mat["NU"], rho_g=mat["RO"])
    classify_legs(model, FAMILY)
    return model, m, ld


def classify_legs(model, family_of_section):
    """Family by geometry: a bar joining two corner nodes of the same leg is a chord, whatever its section.
    Legs that carry a non-chord section are flagged (bar.wrong_section = True)."""
    def half(z):
        return max(abs(p[0]) for p in model.nodes.values() if abs(p[2] - z) < 1e-6)

    def corner(n):
        x, y, z = model.nodes[n]
        h = half(z)
        return abs(abs(x) - h) < 1e-6 and abs(abs(y) - h) < 1e-6

    chord_section = next(k for k, v in family_of_section.items() if v == "chord")
    for b in model.bars:
        (xi, yi, _), (xj, yj, _) = model.nodes[b.i], model.nodes[b.j]
        is_leg = corner(b.i) and corner(b.j) and np.sign(xi) == np.sign(xj) and np.sign(yi) == np.sign(yj)
        b.wrong_section = is_leg and b.section.name != chord_section
        if is_leg:
            b.family = "chord"
        elif b.family == "chord":
            b.family = "diagonal"


def robot_nodal_loads(model, ld, case):
    """Nodal force vector (N) of a Robot simple case made of nodal forces."""
    F = np.zeros(model.ndof)
    for r in ld["cases"][str(case)]["records"]:
        for tok in r["objects"].split():
            if int(tok) not in model.nodes:
                print(f"  warning: load on stray node {tok} ignored ({r['fx']:.1f}, {r['fy']:.1f}, {r['fz']:.1f}) N")
                continue
            d = model.dofs(int(tok))
            F[d[0]] += r["fx"]
            F[d[1]] += r["fy"]
            F[d[2]] += r["fz"]
    return F


def robot_axial(m, case):
    """Robot axial force at mid-length per bar, converted to tension positive (Robot FX > 0 is compression)."""
    return {int(b): -v[1][0] for b, v in m["bar_forces"][str(case)].items()}
