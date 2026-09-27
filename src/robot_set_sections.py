"""Replace the sections of each bar family in a copy of the Robot model, recalculate and save it.

    python src/robot_set_sections.py robot/pylone_dimensionnement_original.rtd robot/pylone_sections_rapport.rtd
"""
import sys
from pathlib import Path

import win32com.client
from win32com.client import CastTo, constants as C

NEW = {"CAEP 90x12": "CAEP 60x8", "CAEP 60x8": "CAEP 50x6", "CAEP 30x5": "CAEP 25x3"}  # verification report
if "--secondary30" in sys.argv:
    NEW["CAEP 30x5"] = "CAEP 30x5"  # state of the member notes


def main(src, dst):
    app = win32com.client.gencache.EnsureDispatch("Robot.Application")
    app.Visible = True
    app.Project.Open(str(Path(src).resolve()))
    s = app.Project.Structure
    for new in set(NEW.values()):
        lab = s.Labels.Create(C.I_LT_BAR_SECTION, new)
        data = CastTo(lab.Data, "IRobotBarSectionData")
        if not data.LoadFromDBase(new):
            raise RuntimeError(f"{new} not found in the section database")
        s.Labels.Store(lab)
    col = s.Bars.GetAll()
    bars = [CastTo(col.Get(i), "IRobotBar") for i in range(1, col.Count + 1)]
    old = {b.Number: b.GetLabel(C.I_LT_BAR_SECTION).Name for b in bars}  # read all before changing
    for b in bars:
        b.SetLabel(C.I_LT_BAR_SECTION, NEW[old[b.Number]])
    app.Project.CalcEngine.Calculate()
    app.Project.SaveAs(str(Path(dst).resolve()))
    print("saved", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
