"""Linear-elastic 3D frame / truss solver (6 DOF per node) with modal analysis.

Units: SI (N, m, Pa). Local axes: x along the bar; for non-vertical bars the reference
vector is global Z, for vertical bars it is global X; the section is then rotated by gamma.
Axial forces do not depend on the section orientation; bending results are indicative.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import eigh


@dataclass
class Section:
    name: str
    A: float
    Iy: float  # principal, strong axis
    Iz: float  # principal, weak axis
    J: float
    Wy: float = 0.0
    Wz: float = 0.0
    width: float = 0.0  # leg width, used for wind exposure


@dataclass
class Bar:
    n: int
    i: int
    j: int
    section: Section
    gamma_deg: float = 0.0
    pinned: bool = False  # True: truss member (axial only)
    family: str = ""


@dataclass
class Model:
    nodes: dict            # node number -> (x, y, z)
    bars: list             # list[Bar]
    supports: dict         # node number -> tuple of 6 booleans (fixed DOFs)
    E: float = 210e9
    nu: float = 0.3
    rho_g: float = 77010.0  # unit weight, N/m3
    _index: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        self._index = {n: k for k, n in enumerate(sorted(self.nodes))}

    @property
    def ndof(self):
        return 6 * len(self.nodes)

    def dofs(self, node):
        k = self._index[node]
        return list(range(6 * k, 6 * k + 6))

    def length(self, bar):
        return float(np.linalg.norm(np.subtract(self.nodes[bar.j], self.nodes[bar.i])))

    # ------------------------------------------------------------------ element
    def rotation(self, bar):
        xi, xj = np.array(self.nodes[bar.i]), np.array(self.nodes[bar.j])
        ex = (xj - xi) / np.linalg.norm(xj - xi)
        ref = np.array([1.0, 0, 0]) if abs(ex[2]) > 0.999 else np.array([0, 0, 1.0])
        ey = np.cross(ref, ex)
        ey /= np.linalg.norm(ey)
        ez = np.cross(ex, ey)
        g = np.radians(bar.gamma_deg)
        ey, ez = np.cos(g) * ey + np.sin(g) * ez, -np.sin(g) * ey + np.cos(g) * ez
        return np.vstack([ex, ey, ez])

    def k_local(self, bar):
        s, L, E = bar.section, self.length(bar), self.E
        G = E / (2 * (1 + self.nu))
        k = np.zeros((12, 12))
        ea = E * s.A / L
        k[0, 0] = k[6, 6] = ea
        k[0, 6] = k[6, 0] = -ea
        if bar.pinned:
            return k
        gj = G * s.J / L
        k[3, 3] = k[9, 9] = gj
        k[3, 9] = k[9, 3] = -gj
        for (v, t, I, sgn) in ((1, 5, s.Iz, 1), (2, 4, s.Iy, -1)):
            a, b, c, d = 12 * E * I / L**3, 6 * E * I / L**2, 4 * E * I / L, 2 * E * I / L
            idx = [v, t, v + 6, t + 6]
            m = np.array([[a, sgn * b, -a, sgn * b],
                          [sgn * b, c, -sgn * b, d],
                          [-a, -sgn * b, a, -sgn * b],
                          [sgn * b, d, -sgn * b, c]])
            for p in range(4):
                for q in range(4):
                    k[idx[p], idx[q]] += m[p, q]
        return k

    def T(self, bar):
        R = self.rotation(bar)
        T = np.zeros((12, 12))
        for b in range(4):
            T[3 * b:3 * b + 3, 3 * b:3 * b + 3] = R
        return T

    # ------------------------------------------------------------------ assembly
    def stiffness(self):
        K = np.zeros((self.ndof, self.ndof))
        for bar in self.bars:
            T = self.T(bar)
            ke = T.T @ self.k_local(bar) @ T
            d = self.dofs(bar.i) + self.dofs(bar.j)
            K[np.ix_(d, d)] += ke
        # small rotational springs at nodes where only truss members meet
        diag = np.diag(K).copy()
        for n in self.nodes:
            for r in self.dofs(n)[3:]:
                if diag[r] == 0:
                    K[r, r] = 1.0
        return K

    def self_weight(self):
        """Nodal loads (N) for self weight, half of each bar weight to each end."""
        F = np.zeros(self.ndof)
        for bar in self.bars:
            w = bar.section.A * self.rho_g * self.length(bar)
            F[self.dofs(bar.i)[2]] -= w / 2
            F[self.dofs(bar.j)[2]] -= w / 2
        return F

    def free(self):
        fixed = set()
        for n, fx in self.supports.items():
            fixed.update(d for d, f in zip(self.dofs(n), fx) if f)
        return np.array([d for d in range(self.ndof) if d not in fixed])

    def solve(self, F, K=None):
        K = self.stiffness() if K is None else K
        fr = self.free()
        u = np.zeros(self.ndof)
        u[fr] = np.linalg.solve(K[np.ix_(fr, fr)], F[fr])
        return u

    def bar_end_forces(self, u):
        """Local end forces per bar: dict bar.n -> array(12) [N, Vy, Vz, Mx, My, Mz] at i then j.
        Axial force N > 0 is tension (Robot sign convention)."""
        out = {}
        for bar in self.bars:
            d = self.dofs(bar.i) + self.dofs(bar.j)
            f = self.k_local(bar) @ (self.T(bar) @ u[d])
            out[bar.n] = f
        return out

    @staticmethod
    def axial(f):
        return -f[0]  # tension positive

    # ------------------------------------------------------------------ modal
    def modal(self, n_modes=6, extra_mass=None):
        """Natural periods (s) with lumped translational masses from self weight."""
        K = self.stiffness()
        m = np.zeros(self.ndof)
        for bar in self.bars:
            mass = bar.section.A * self.rho_g / 9.81 * self.length(bar)
            for n in (bar.i, bar.j):
                for d in self.dofs(n)[:3]:
                    m[d] += mass / 2
        if extra_mass:
            for n, mass in extra_mass.items():
                for d in self.dofs(n)[:3]:
                    m[d] += mass
        for n in self.nodes:  # tiny rotational inertia keeps M positive definite
            for d in self.dofs(n)[3:]:
                m[d] += 1e-6
        fr = self.free()
        w2, phi = eigh(K[np.ix_(fr, fr)], np.diag(m[fr]), subset_by_index=[0, n_modes - 1])
        periods = 2 * np.pi / np.sqrt(w2)
        return periods, phi
