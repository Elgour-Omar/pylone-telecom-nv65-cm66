# 25 m Telecom Lattice Tower: NV65 Wind and CM66 Member Checks

🇫🇷 [Résumé en français plus bas](#résumé-en-français)

I modelled a 25 m self-supporting telecom tower in **Autodesk Robot Structural Analysis**, then checked it independently in two ways: a hand calculation in **Calcpad** and a **Python** tool that drives Robot through its API and recomputes the tower with its own 3D solver. The two checks agree with Robot, and they also found errors in my own Robot model that Robot's "section OK" did not show. This repository documents the model, the checks, what they found, and the fixes I am making.

<p align="center">
  <img src="docs/robot_3d_model.png" width="48%" alt="Robot model of the tower">
  <img src="results/utilisation.png" width="30%" alt="Member utilisation map">
</p>

## The structure

| | |
|---|---|
| Type | Self-supporting square lattice tower, bolted equal-leg angles |
| Height | 25 m: tapered trunk 0 to 20 m (5 m to 1 m wide), straight 1 × 1 m mast 20 to 25 m |
| Members | 382 bars: legs L60×8, diagonals L50×6, secondary (redundant) members L25×3, steel E24 |
| Loads | Self weight and NV65 wind (region 1, normal site, as assumed in the model) |
| Codes | NV65 (wind on lattice towers), CM66 with Additif 80 (member checks) |

## What is in the repository

| Folder | Content |
|---|---|
| [`calcpad/`](calcpad) | Hand calculation note (French): NV65 wind section by section, shear and overturning moment, leg, diagonal and secondary member checks. [PDF](calcpad/Pylone_telecom_25m_NV65_CM66.pdf) |
| [`src/`](src) | Python tool: Robot API scripts, 3D frame solver with modal analysis, NV65 wind, CM66 checks, Excel report |
| [`robot/`](robot) | Robot models: the original, and the version with the sections of my verification report |
| [`data/`](data) | Model data extracted from Robot (JSON), so the Python tool runs without Robot |
| [`results/`](results) | Excel reports, plots and printed summaries |
| [`tests/`](tests) | Automatic checks of the Python tool against values printed by Robot |

## Method

**1. Wind (NV65).** For each section of the tower: solidity ratio φ = Sp / S, drag coefficient Ct = 3.2 − 2φ for angles (× (1 + 0.6φ) for wind on the diagonal), height effect 2.5 (H + 18) / (H + 60), size effect δ, and dynamic coefficient β = θ (1 + ξτ). The natural period needed for β comes from a modal analysis: the first sway mode is at **T ≈ 0.20 s**, so the tower is stiff and β stays close to 1.

**2. Analysis.** The Python tool rebuilds the Robot model (165 nodes, 382 bars, real section properties and orientations) in its own 3D frame solver, applies the CM66 load combinations (4/3 G + 3/2 W, G + 3/2 W, G + 1.75 W extreme) and checks **8 wind directions** instead of the 2 in the Robot model.

**3. Member checks (CM66, Additif 80).** Buckling coefficient k0 = 1/χ with buckling curve c for angles, check k0·N ≤ A·σe, and slenderness limits (legs 120, bracing 200, secondary members 250).

**4. Hand calculation (Calcpad).** Shear and overturning moment in closed form, leg forces (2 legs for wind on a face, 1 corner leg for diagonal wind), shear shared between the inclined legs and the diagonals, and the usual 2.5 % rule for secondary members.

## Validation

| Check | Result |
|---|---|
| Max compression per family, same loads as Robot (self weight and both wind cases) | within **2 %** of Robot |
| Top displacement | 7.42 mm (Python) vs 7.43 mm (Robot) |
| NV65 wind per section | within about **5 %** of Robot's wind note (outline areas identical; small difference in how exposed widths are measured) |
| Buckling coefficient k0 | identical to Robot's notes (4.48, 1.76, 14.18) |
| Calcpad hand calculation vs 3D model, leg at 10 m | 19.9 kN vs 20.1 kN, ratio 0.42 in both |

Run the checks with `python -m unittest discover tests`.

## What the independent checks found

These are errors in my own Robot model. Robot reported every family as correct, because each check only covers what the model contains.

1. **Leg segments with the wrong section.** Between 6 and 8 m, two leg segments carry the secondary member section, and one leg between 20 and 25 m carries the diagonal section. Under diagonal wind from a direction the model did not include, the leg at 6 to 7 m reaches a ratio of about **4** (red bars in the utilisation map).
2. **Only 2 of 8 wind directions** were checked in the model.
3. **Diagonals not connected to the secondary members.** 18 diagonals pass through the mid-point node of the secondary bracing without being connected to it, so they buckle over their full length: slenderness **331** instead of about **165** once connected.
4. **Slenderness above the usual limits** even where strength is fine: legs 174 (limit 120) between 10 and 20 m, secondary members 303 (limit 250).
5. **Inconsistent files.** The saved model, my verification report and my member notes were produced with different section sets, and the wind loads were not regenerated after the sections changed.

With the leg sections corrected, strength is comfortable (ratios about 0.4 for legs and diagonals). The design issue is slenderness, not strength ([`results/summary_legs_fixed.txt`](results/summary_legs_fixed.txt)).

## Fixes in progress

- [ ] Give every leg segment the leg section (L60×8)
- [ ] Connect the 18 diagonals at the mid-point nodes of the secondary bracing
- [ ] Add a secondary member at mid-panel on the legs between 10 and 20 m
- [ ] Secondary members L35×4
- [ ] Regenerate the wind in all directions, with the period from the modal analysis
- [ ] Re-run Robot's checks and update this repository

## Run it

```bash
pip install -r requirements.txt
python src/run_design.py              # model as it is
python src/run_design.py --fix-legs   # with the leg sections corrected
python -m unittest discover tests
```

The scripts in `src/robot_*.py` need Robot Structural Analysis 2015 on Windows (Robot API through `pywin32`). Everything else runs from the JSON files in `data/`.

## Limits

Bolted connections, base plates, anchor bolts and foundations are not covered. The wind region, site category and the ξ coefficient (NV65 fig. R-III-3) are assumptions to confirm for a real site. This is a self-study project, not a design for construction.

## References

- Règles NV65 (neige et vent), chapter III, lattice towers
- Règles CM66 and Additif 80
- Learning references I used: A. Benchekroun, *Dimensionnement d'un pylône* (2015); S. Hadi and N. Mezhoud, *Analyse de la stabilité des pylônes à treillis*, Master's thesis, Université Badji Mokhtar Annaba (2016)

---

## Résumé en français

J'ai modélisé un pylône télécom autostable de 25 m sous Robot Structural Analysis, puis je l'ai vérifié de deux façons indépendantes : une note de calcul manuelle sous Calcpad et un outil Python qui pilote Robot par son API et recalcule la tour avec son propre solveur 3D. Les deux vérifications concordent avec Robot (écarts de 2 à 5 %), et elles ont révélé des erreurs dans mon propre modèle : membrures avec une mauvaise section entre 6 et 8 m, seulement 2 directions de vent sur 8, et 18 diagonales non reliées aux barres secondaires, d'où un élancement de 331 au lieu d'environ 165. Une fois les membrures corrigées, la résistance est largement suffisante ; le vrai sujet est l'élancement. Les corrections sont en cours (voir la liste ci-dessus).

**Omar Elgour**, Ingénieur d'État en Génie Civil (EMSI Marrakech) · [LinkedIn](https://www.linkedin.com/in/omar-elgour)
