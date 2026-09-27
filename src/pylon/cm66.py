"""Member checks, CM66 with Additif 80 (as implemented in Robot).

Buckling coefficient k0 = 1/chi with the Additif 80 buckling curve c (alpha = 0.49),
which reproduces the k0 values printed in Robot's CM66 notes (e.g. lambda = 174.06 -> k0 = 4.48).
"""
import math

E = 210e9
FY = 235e6          # E24
ALPHA_C = 0.49      # curve c, angles


def lambda_1(fy=FY, e=E):
    return math.pi * math.sqrt(e / fy)


def k0(slenderness, fy=FY, alpha=ALPHA_C):
    lb = slenderness / lambda_1(fy)
    phi = 0.5 * (1 + alpha * (lb - 0.2) + lb * lb)
    chi = min(1.0, 1 / (phi + math.sqrt(max(phi * phi - lb * lb, 0))))
    return 1 / chi


def axial_check(N, A, Lk_y, Lk_z, Iy, Iz, fy=FY):
    """Check 5.31 (compression) or N/Np (tension). N > 0 tension. Returns dict."""
    iy, iz = math.sqrt(Iy / A), math.sqrt(Iz / A)
    lam_y, lam_z = Lk_y / iy, Lk_z / iz
    Np = A * fy
    if N >= 0:
        ratio, k = N / Np, 1.0
    else:
        k = max(k0(lam_y, fy), k0(lam_z, fy))
        ratio = k * (-N) / Np
    return dict(lam_y=lam_y, lam_z=lam_z, k0=k, Np=Np, ratio=ratio)


SLENDERNESS_LIMITS = {  # usual limits for lattice towers (compression members)
    "chord": 120,
    "diagonal": 200,
    "secondary": 250,
}
