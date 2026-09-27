"""Extract geometry, sections, load cases and results from a Robot Structural Analysis model.

Uses the Robot COM API (RobotOM) through pywin32. Robot must be installed and licensed.
Always run it on a copy of the .rtd file.

    python src/robot_extract.py robot/pylone_sections_rapport.rtd data/robot_model_rapport.json
"""
import json
import sys
from pathlib import Path

import win32com.client
from win32com.client import CastTo, constants as C


def cast(obj, iface):
    return CastTo(obj, iface)


def collection(server, iface):
    col = server.GetAll()
    return [cast(col.Get(i), iface) for i in range(1, col.Count + 1)]


def label_name(obj, label_type):
    try:
        if obj.HasLabel(label_type):
            return obj.GetLabel(label_type).Name
    except Exception:
        pass
    return None


def main(rtd, out_json, calculate=False):
    app = win32com.client.gencache.EnsureDispatch("Robot.Application")
    app.Visible = True
    app.Interactive = True
    app.Project.Open(str(Path(rtd).resolve()))
    s = app.Project.Structure

    nodes = [dict(n=nd.Number, x=nd.X, y=nd.Y, z=nd.Z,
                  support=label_name(nd, C.I_LT_SUPPORT))
             for nd in collection(s.Nodes, "IRobotNode")]

    bars = []
    for b in collection(s.Bars, "IRobotBar"):
        bars.append(dict(
            n=b.Number, i=b.StartNode, j=b.EndNode, length=b.Length,
            section=label_name(b, C.I_LT_BAR_SECTION),
            release=label_name(b, C.I_LT_BAR_RELEASE),
            member_type=label_name(b, C.I_LT_MEMBER_TYPE),
            material=label_name(b, C.I_LT_MATERIAL),
        ))

    cases = []
    for c in collection(s.Cases, "IRobotCase"):
        d = dict(n=c.Number, name=c.Name, nature=int(c.Nature), type=int(c.Type))
        if c.Type == C.I_CT_COMBINATION:
            cc = cast(c, "IRobotCaseCombination")
            d["factors"] = [dict(case=cc.CaseFactors.Get(k).CaseNumber, factor=cc.CaseFactors.Get(k).Factor)
                            for k in range(1, cc.CaseFactors.Count + 1)]
        elif c.Type == C.I_CT_SIMPLE:
            sc = cast(c, "IRobotSimpleCase")
            d["n_records"] = sc.Records.Count
            d["analysis"] = int(sc.AnalizeType)
        cases.append(d)

    if calculate or not app.Project.Structure.Results.Available:
        app.Project.CalcEngine.Calculate()

    res = s.Results
    forces, disp = {}, {}
    for c in cases:
        key = str(c["n"])
        try:
            forces[key] = {str(b["n"]): [
                (lambda f: [f.FX, f.FY, f.FZ, f.MX, f.MY, f.MZ])(res.Bars.Forces.Value(b["n"], c["n"], p))
                for p in (0.0, 0.5, 1.0)] for b in bars}
            disp[key] = {str(nd["n"]): (lambda u: [u.UX, u.UY, u.UZ, u.RX, u.RY, u.RZ])(
                res.Nodes.Displacements.Value(nd["n"], c["n"])) for nd in nodes}
        except Exception as e:  # e.g. case without results
            forces[key] = {"error": str(e)}

    out = dict(source=str(rtd), nodes=nodes, bars=bars, cases=cases,
               bar_forces_units="N and N*m, positions 0/0.5/1 along the bar",
               bar_forces=forces, node_displacements=disp)
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(out_json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(nodes)} nodes, {len(bars)} bars, {len(cases)} cases -> {out_json}")
    return app


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], calculate="--calc" in sys.argv)
