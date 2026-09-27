"""NV65 wind on a square lattice tower made of angles (Règles NV65, chap. III, pylônes).

Global method per section, as in Robot's NV65 tower generator:
    T = q10 * (qH/q10) * ks * km * delta * beta * Ct * Sp
    qH/q10 = 2.5 (H + 18) / (H + 60)                       height effect
    Ct = 3.2 - 2 phi   (wind normal to a face, angles)
    Ct_diag = Ct * (1 + 0.6 phi)   (wind along the diagonal)
    phi = Sp / S   (solidity ratio of the windward face)
    beta = theta * (1 + xi * tau)  dynamic coefficient (xi from the period, NV65 fig. R-III-3)
delta, tau and xi are read from the NV65 charts; they are inputs here.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class WindInput:
    q10: float = 500.0      # N/m2 (50 daN/m2, region 1, normal wind)
    ks: float = 1.0         # site effect
    km: float = 1.0         # mask effect
    delta: float = 0.778    # size reduction (NV65 fig. R-III-2)
    theta: float = 1.0
    xi: float = 0.0         # pulsation coefficient, from the period (0 -> beta = 1)
    tau: float = 0.36       # response coefficient
    extreme: bool = False   # True -> extreme wind = 1.75 x normal

    @property
    def beta(self):
        return self.theta * (1 + self.xi * self.tau)


def height_factor(H):
    return 2.5 * (H + 18) / (H + 60)


def half_width_at(model, z, tol=1e-6):
    xs = [abs(p[0]) for p in model.nodes.values() if abs(p[2] - z) < tol]
    return max(xs)


def face_bars(model, sign=-1, axis=0, tol=1e-3):
    """Bars lying in the face x = sign * halfwidth(z) (windward face for wind along +x)."""
    def on_face(n):
        p = model.nodes[n]
        return abs(p[axis] - sign * half_width_at(model, p[2])) < tol
    return [b for b in model.bars if on_face(b.i) and on_face(b.j)]


def section_areas(model, z0, z1, axis=0):
    """Solid area Sp (bars of one face, projected on the plane normal to the wind) and outline area S."""
    Sp = 0.0
    z_top = max(p[2] for p in model.nodes.values())
    for b in face_bars(model, axis=axis):
        zi, zj = model.nodes[b.i][2], model.nodes[b.j][2]
        lo, hi = min(zi, zj), max(zi, zj)
        if abs(hi - lo) < 1e-9:  # horizontal bar: belongs to the panel starting at its level
            if not (z0 - 1e-9 <= lo < z1 - 1e-9 or (abs(lo - z_top) < 1e-9 and abs(z1 - z_top) < 1e-9)):
                continue
        elif hi <= z0 + 1e-9 or lo >= z1 - 1e-9:
            continue
        pi, pj = np.array(model.nodes[b.i]), np.array(model.nodes[b.j])
        d = pj - pi
        d[axis] = 0.0                          # projection on the plane normal to the wind
        L = np.linalg.norm(d)
        frac = 1.0 if hi == lo else (min(hi, z1) - max(lo, z0)) / (hi - lo)
        Sp += b.section.width * L * frac
    levels = sorted({round(p[2], 6) for p in model.nodes.values()})
    zs = [z for z in levels if z0 - 1e-9 <= z <= z1 + 1e-9]
    widths = [2 * half_width_at(model, z) for z in zs]
    S = float(np.trapezoid(widths, zs))
    return Sp, S


def section_forces(model, sections, w: WindInput):
    """sections: list of (name, z0, z1). Returns list of dicts, force T in N."""
    out = []
    q = w.q10 * (1.75 if w.extreme else 1.0)
    for name, z0, z1 in sections:
        Sp, S = section_areas(model, z0, z1)
        phi = Sp / S
        ct = 3.2 - 2 * phi
        ct_d = ct * (1 + 0.6 * phi)
        base = q * height_factor(z1) * w.ks * w.km * w.delta * w.beta * Sp
        out.append(dict(section=name, z0=z0, z1=z1, Sp=Sp, S=S, phi=phi, Ct=ct, Ct_diag=ct_d,
                        qH_q10=height_factor(z1), T_normal=base * ct, T_diag=base * ct_d))
    return out


def nodal_loads(model, sections, w: WindInput, direction="normal", q_at="section_top"):
    """Distribute the section wind force over the tower nodes, panel by panel.

    Each panel between two consecutive levels gets q(z) * ... * Ct * Sp_panel; half goes to the
    4 leg nodes of each level. q_at = 'section_top' (as Robot's global note) or 'panel_mid'.
    """
    F = np.zeros(model.ndof)
    q = w.q10 * (1.75 if w.extreme else 1.0)
    info = {s["section"]: s for s in section_forces(model, sections, w)}
    levels = sorted({round(p[2], 6) for p in model.nodes.values()})
    leg_levels = [z for z in levels if sum(1 for p in model.nodes.values()
                                           if abs(p[2] - z) < 1e-6 and
                                           abs(abs(p[0]) - half_width_at(model, z)) < 1e-6 and
                                           abs(abs(p[1]) - half_width_at(model, z)) < 1e-6) == 4]
    for za, zb in zip(leg_levels[:-1], leg_levels[1:]):
        name, z0, z1 = next(s for s in sections if s[1] - 1e-9 <= za and zb <= s[2] + 1e-9)
        s = info[name]
        Sp_panel, _ = section_areas(model, za, zb)
        H = z1 if q_at == "section_top" else (za + zb) / 2
        ct = s["Ct"] if direction == "normal" else s["Ct_diag"]
        T = q * height_factor(H) * w.ks * w.km * w.delta * w.beta * ct * Sp_panel
        for z in (za, zb):
            legs = [n for n, p in model.nodes.items() if abs(p[2] - z) < 1e-6 and
                    abs(abs(p[0]) - half_width_at(model, z)) < 1e-6 and
                    abs(abs(p[1]) - half_width_at(model, z)) < 1e-6]
            for n in legs:
                d = model.dofs(n)
                if direction == "normal":
                    F[d[0]] += T / 2 / 4
                else:
                    F[d[0]] += T / 2 / 4 / np.sqrt(2)
                    F[d[1]] -= T / 2 / 4 / np.sqrt(2)
    return F
