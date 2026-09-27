"""Independent check of the 25 m telecom lattice tower: NV65 wind + CM66 (Additif 80) member checks.

    python src/run_design.py            (from the repository root)

    python src/run_design.py --fix-legs (all leg segments given the chord section)

Inputs : data/robot_model_rapport.json, data/robot_loads_rapport.json (extracted from Robot)
Outputs: results/tower_check*.xlsx, results/*.png, printed summary
"""
import math
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from pylon import cm66, nv65
from pylon.robot_io import load, robot_axial, robot_nodal_loads

import sys

ROOT = Path(__file__).resolve().parents[1]
FIX_LEGS = "--fix-legs" in sys.argv
DATA = ROOT / "data"
OUT = ROOT / "results"
SECTIONS = [("T1", 0.0, 20.0), ("T2", 20.0, 25.0)]
FAMILIES = ("chord", "diagonal", "secondary")


def rotate(model, F, angle_deg):
    """Rotate a horizontal nodal load pattern about the tower axis (the tower is doubly symmetric)."""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    coords = {n: p for n, p in model.nodes.items()}
    lookup = {(round(p[0], 4), round(p[1], 4), round(p[2], 4)): n for n, p in coords.items()}
    G = np.zeros_like(F)
    for n, (x, y, z) in coords.items():
        d = model.dofs(n)
        fx, fy = F[d[0]], F[d[1]]
        if fx == 0 and fy == 0 and F[d[2]] == 0:
            continue
        xr, yr = c * x - s * y, s * x + c * y
        m = lookup[(round(xr, 4), round(yr, 4), round(z, 4))]
        dm = model.dofs(m)
        G[dm[0]] += c * fx - s * fy
        G[dm[1]] += s * fx + c * fy
        G[dm[2]] += F[d[2]]
    return G


def combos(G, winds):
    """CM66 combinations with self weight G and wind patterns (normal wind, N)."""
    out = {"4/3 G": 4 / 3 * G}
    for name, W in winds.items():
        out[f"4/3 G + 3/2 {name}"] = 4 / 3 * G + 1.5 * W
        out[f"G + 3/2 {name}"] = G + 1.5 * W
        out[f"G + 1.75 {name} (extreme)"] = G + 1.75 * W
    return out


def check_all(model, K, load_cases):
    res = {}
    for cname, F in load_cases.items():
        u = model.solve(F, K)
        forces = model.bar_end_forces(u)
        for bar in model.bars:
            N = model.axial(forces[bar.n])
            L = model.length(bar)
            c = cm66.axial_check(N, bar.section.A, L, L, bar.section.Iy, bar.section.Iz)
            prev = res.get(bar.n)
            if prev is None or c["ratio"] > prev["ratio"]:
                res[bar.n] = dict(c, N=N, combo=cname, family=bar.family, section=bar.section.name, L=L,
                                  wrong_section=getattr(bar, "wrong_section", False))
    return res


def summarize(model, res):
    rows = []
    for fam in FAMILIES:
        items = {b: r for b, r in res.items() if r["family"] == fam}
        gov = max(items, key=lambda b: items[b]["ratio"])
        lam = [max(r["lam_y"], r["lam_z"]) for r in items.values()]
        lim = cm66.SLENDERNESS_LIMITS[fam]
        wrong = {b: r for b, r in items.items() if r["wrong_section"]}
        rows.append(dict(family=fam, section=items[gov]["section"], bars=len(items), bar=gov,
                         wrong_n=len(wrong), wrong_max=max((r["ratio"] for r in wrong.values()), default=0.0),
                         ratio=items[gov]["ratio"], N_kN=items[gov]["N"] / 1e3, k0=items[gov]["k0"],
                         combo=items[gov]["combo"], lam_max=max(lam), lam_limit=lim,
                         over_limit=sum(x > lim for x in lam)))
    return rows


def main():
    model, m, ld = load(DATA / "robot_model_rapport.json", DATA / "robot_loads_rapport.json", state="report")
    if FIX_LEGS:  # give every leg segment the chord section
        chord = next(b.section for b in model.bars if b.family == "chord" and not b.wrong_section)
        fixed = [b.n for b in model.bars if b.wrong_section]
        for b in model.bars:
            if b.wrong_section:
                b.section, b.wrong_section = chord, False
        print(f"legs corrected to {chord.name}: bars {fixed}")
    K = model.stiffness()
    G = model.self_weight()
    report = {}

    # 1. solver validation against Robot (same loads)
    valid = []
    for case, F in ((1, G), (4, robot_nodal_loads(model, ld, 4)), (5, robot_nodal_loads(model, ld, 5))):
        f = model.bar_end_forces(model.solve(F, K))
        R = robot_axial(m, case)
        for fam in FAMILIES:
            bs = [b.n for b in model.bars if b.family == fam]
            py, rb = min(model.axial(f[b]) for b in bs), min(R[b] for b in bs)
            valid.append(dict(case=ld["cases"][str(case)]["name"], family=fam, python_kN=py / 1e3,
                              robot_kN=rb / 1e3, diff_pct=100 * (py - rb) / rb if rb else 0.0))
    report["validation"] = valid

    # 2. natural periods
    T, _ = model.modal(8)
    report["periods"] = T

    # 3. wind: Robot's applied nodal loads vs NV65 recomputed
    W_robot = {"W normal (Robot)": robot_nodal_loads(model, ld, 4), "W diagonal (Robot)": robot_nodal_loads(model, ld, 5)}
    scenarios = {}
    for beta_label, xi in (("beta=1.00", 0.0), ("beta=1.05", 0.05 / 0.36), ("beta=1.10", 0.10 / 0.36)):
        w = nv65.WindInput(xi=xi, tau=0.36)
        Wn = nv65.nodal_loads(model, SECTIONS, w, "normal")
        Wd = nv65.nodal_loads(model, SECTIONS, w, "diagonal")
        winds = {}
        for k, ang in enumerate((0, 90, 180, 270)):
            winds[f"W normal {ang}deg"] = rotate(model, Wn, ang)
            winds[f"W diagonal {ang - 45 if ang else 315}deg"] = rotate(model, Wd, ang)
        scenarios[f"NV65 Python, {beta_label}, 8 directions"] = (winds, w)
    report["wind_sections"] = nv65.section_forces(model, SECTIONS, nv65.WindInput())
    report["wind_totals"] = {"Robot applied, normal": float(W_robot["W normal (Robot)"][0::6].sum()) / 10,
                             "Robot applied, diagonal": math.hypot(W_robot["W diagonal (Robot)"][0::6].sum(),
                                                                   W_robot["W diagonal (Robot)"][1::6].sum()) / 10,
                             "Robot note, normal": 1429.20, "Robot note, diagonal": 1584.64}

    # 4. member checks
    results = {"Robot wind loads (as modelled)": check_all(model, K, combos(G, W_robot))}
    for name, (winds, _) in scenarios.items():
        results[name] = check_all(model, K, combos(G, winds))
    report["summaries"] = {k: summarize(model, v) for k, v in results.items()}

    # 5. serviceability: top displacement under G + W (normal wind, beta=1)
    winds0, _ = scenarios["NV65 Python, beta=1.00, 8 directions"]
    top_nodes = [n for n, p in model.nodes.items() if abs(p[2] - 25.0) < 1e-6]
    disp = {}
    for wn, W in list(winds0.items())[:2]:
        u = model.solve(G + W, K)
        disp[wn] = max(math.hypot(u[model.dofs(n)[0]], u[model.dofs(n)[1]]) for n in top_nodes) * 1e3
    report["top_disp_mm"] = disp

    print_report(report)
    write_excel(report, results)
    plots(model, report, results)


def print_report(r):
    print("\n== Solver validation (max compression, kN) ==")
    for v in r["validation"]:
        print(f"  {v['case'][:32]:32s} {v['family']:9s} python {v['python_kN']:8.2f}  robot {v['robot_kN']:8.2f}  ({v['diff_pct']:+.1f}%)")
    print("\n== Periods (s):", np.round(r["periods"][:6], 3))
    print("\n== NV65 per section (normal wind, beta = 1) ==")
    for s in r["wind_sections"]:
        print(f"  {s['section']}: Sp={s['Sp']:.2f} m2  S={s['S']:.1f} m2  phi={s['phi']:.3f}  Ct={s['Ct']:.3f}  "
              f"T={s['T_normal'] / 10:.1f} daN  T_diag={s['T_diag'] / 10:.1f} daN")
    print("  totals (daN):", {k: round(v, 1) for k, v in r["wind_totals"].items()})
    for name, rows in r["summaries"].items():
        print(f"\n== Member checks: {name} ==")
        for x in rows:
            print(f"  {x['family']:9s} {x['section']:10s} max ratio {x['ratio']:.2f} (bar {x['bar']}, N={x['N_kN']:.2f} kN, "
                  f"k0={x['k0']:.2f}, {x['combo']})  lambda max {x['lam_max']:.0f} / limit {x['lam_limit']} -> {x['over_limit']} bars over" + (f" | legs with wrong section: {x['wrong_n']} (max ratio {x['wrong_max']:.2f})" if x['wrong_n'] else ""))
    print("\n== Top displacement G + W (mm):", {k: round(v, 1) for k, v in r["top_disp_mm"].items()}, "| H/100 = 250 mm")


def write_excel(r, results):
    wb = Workbook()
    bold, head = Font(bold=True), PatternFill("solid", fgColor="1F3A5F")
    white = Font(bold=True, color="FFFFFF")

    def sheet(title, header, rows):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = white, head
        for row in rows:
            ws.append(row)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(12, min(45, max(len(str(c.value or "")) for c in col) + 2))
        return ws

    ws = wb.active
    ws.title = "Summary"
    ws.append(["25 m telecom lattice tower: independent NV65 / CM66 check"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Periods (s)"] + [round(t, 3) for t in r["periods"][:6]])
    ws.append([])
    for name, rows in r["summaries"].items():
        ws.append([name]); ws.cell(ws.max_row, 1).font = bold
        ws.append(["family", "section", "max ratio", "bar", "N (kN)", "k0", "combination", "lambda max", "limit", "bars over limit"])
        for x in rows:
            ws.append([x["family"], x["section"], round(x["ratio"], 3), x["bar"], round(x["N_kN"], 2), round(x["k0"], 2),
                       x["combo"], round(x["lam_max"], 1), x["lam_limit"], x["over_limit"]])
        ws.append([])
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["G"].width = 38

    sheet("Validation vs Robot", ["load case", "family", "python max compression (kN)", "robot (kN)", "diff %"],
          [[v["case"], v["family"], round(v["python_kN"], 3), round(v["robot_kN"], 3), round(v["diff_pct"], 2)] for v in r["validation"]])
    sheet("NV65 sections", ["section", "z0", "z1", "Sp (m2)", "S (m2)", "phi", "qH/q10", "Ct", "Ct diag", "T normal (daN)", "T diag (daN)"],
          [[s["section"], s["z0"], s["z1"], round(s["Sp"], 3), round(s["S"], 2), round(s["phi"], 3), round(s["qH_q10"], 3),
            round(s["Ct"], 3), round(s["Ct_diag"], 3), round(s["T_normal"] / 10, 1), round(s["T_diag"] / 10, 1)] for s in r["wind_sections"]]
          + [[k, "", "", "", "", "", "", "", "", round(v, 1)] for k, v in r["wind_totals"].items()])
    for name, res in results.items():
        title = ("Bars - " + name.replace("NV65 Python, ", "").replace(", 8 directions", "").replace("Robot wind loads (as modelled)", "robot wind"))[:31]
        sheet(title, ["bar", "family", "section", "L (m)", "N (kN)", "lambda y", "lambda z", "k0", "ratio", "combination"],
              [[b, x["family"], x["section"], round(x["L"], 3), round(x["N"] / 1e3, 3), round(x["lam_y"], 1), round(x["lam_z"], 1),
                round(x["k0"], 2), round(x["ratio"], 3), x["combo"]] for b, x in sorted(res.items())])
    name = "tower_check_legs_fixed.xlsx" if FIX_LEGS else "tower_check.xlsx"
    wb.save(OUT / name)
    print("\nwritten results/" + name)


def plots(model, r, results):
    # wind pressure profile
    z = np.linspace(0, 25, 101)
    q = 50 * np.array([nv65.height_factor(h) for h in z]) * 0.778
    fig, ax = plt.subplots(figsize=(4, 6))
    ax.plot(q, z)
    ax.set_xlabel("NV65 normal wind pressure q x delta (daN/m2)")
    ax.set_ylabel("height (m)")
    ax.set_title("Wind profile (region 1, normal site)")
    ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(OUT / "wind_profile.png", dpi=150); plt.close(fig)

    # utilisation map (front view), NV65 beta = 1
    res = results["NV65 Python, beta=1.00, 8 directions"]
    fig, ax = plt.subplots(figsize=(5, 8))
    cmap = plt.get_cmap("RdYlGn_r")
    for bar in model.bars:
        (x1, y1, z1), (x2, y2, z2) = model.nodes[bar.i], model.nodes[bar.j]
        ratio = res[bar.n]["ratio"]
        ax.plot([x1 + 0.35 * y1, x2 + 0.35 * y2], [z1, z2], color=cmap(min(ratio, 1.0)), lw=1 + 2 * min(ratio, 1))
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=ax, label="CM66 axial ratio k0 N / Np")
    ax.set_aspect("equal"); ax.set_title("Member utilisation (NV65, 8 wind directions)")
    ax.set_xlabel("x (m)"); ax.set_ylabel("z (m)")
    fig.tight_layout(); fig.savefig(OUT / ("utilisation_legs_fixed.png" if FIX_LEGS else "utilisation.png"), dpi=150); plt.close(fig)
    print("written wind_profile.png, utilisation.png")


if __name__ == "__main__":
    main()
