"""Extract load records, section properties, bar orientation and material from the open Robot model.

Opens the model itself (Robot closes when the script that launched it ends):
    python src/robot_extract_loads.py robot/pylone_sections_rapport.rtd data/robot_loads_rapport.json
"""
import json
import sys
from pathlib import Path

import win32com.client
from win32com.client import CastTo, constants as C


def main(rtd, out_json):
    app = win32com.client.gencache.EnsureDispatch("Robot.Application")
    app.Visible = True
    app.Project.Open(str(Path(rtd).resolve()))
    s = app.Project.Structure
    out = dict(sections={}, materials={}, bars={}, cases={})

    # section and material properties, read from the labels attached to the bars
    # (Labels.Get / GetAvailableNames raise errors in Robot 2015)
    col = s.Bars.GetAll()
    bars = [CastTo(col.Get(i), "IRobotBar") for i in range(1, col.Count + 1)]
    for ltype, key, iface in ((C.I_LT_BAR_SECTION, "sections", "IRobotBarSectionData"),
                              (C.I_LT_MATERIAL, "materials", "IRobotMaterialData")):
        for b in bars:
            if not b.HasLabel(ltype):
                continue
            lab = b.GetLabel(ltype)
            name = lab.Name
            if name in out[key]:
                continue
            d = CastTo(lab.Data, iface)
            if key == "sections":
                out[key][name] = {v: d.GetValue(getattr(C, "I_BSDV_" + v)) for v in
                                  ("AX", "AY", "AZ", "IX", "IY", "IZ", "VY", "VPY", "VZ", "VPZ", "WY", "WZ", "D", "BF", "TW", "TF", "GAMMA", "WEIGHT")}
            else:
                out[key][name] = dict(E=d.E, NU=d.NU, RO=d.RO, RE=d.RE)

    # bar orientation (gamma angle)
    for b in bars:
        out["bars"][str(b.Number)] = dict(gamma=b.Gamma)

    # load records of the simple cases
    col = s.Cases.GetAll()
    for i in range(1, col.Count + 1):
        c = CastTo(col.Get(i), "IRobotCase")
        if c.Type != C.I_CT_SIMPLE:
            continue
        sc = CastTo(c, "IRobotSimpleCase")
        recs = []
        for r in range(1, sc.Records.Count + 1):
            rec = sc.Records.Get(r)
            t = int(rec.Type)
            d = dict(type=t, objects=rec.Objects.ToText())
            if t == C.I_LRT_DEAD:
                d.update(x=rec.GetValue(C.I_DRV_X), y=rec.GetValue(C.I_DRV_Y), z=rec.GetValue(C.I_DRV_Z),
                         coeff=rec.GetValue(C.I_DRV_COEFF), entire=rec.GetValue(C.I_DRV_ENTIRE_STRUCTURE))
            elif t == C.I_LRT_NODE_FORCE:
                d.update(fx=rec.GetValue(C.I_NFRV_FX), fy=rec.GetValue(C.I_NFRV_FY), fz=rec.GetValue(C.I_NFRV_FZ),
                         cx=rec.GetValue(C.I_NFRV_CX), cy=rec.GetValue(C.I_NFRV_CY), cz=rec.GetValue(C.I_NFRV_CZ))
            elif t == C.I_LRT_BAR_UNIFORM:
                d.update(px=rec.GetValue(C.I_BURV_PX), py=rec.GetValue(C.I_BURV_PY), pz=rec.GetValue(C.I_BURV_PZ),
                         local=rec.GetValue(C.I_BURV_LOCAL), projected=rec.GetValue(C.I_BURV_PROJECTION))
            recs.append(d)
        out["cases"][str(c.Number)] = dict(name=c.Name, records=recs)

    Path(out_json).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("sections:", list(out["sections"]), "| materials:", out["materials"])
    for k, v in out["cases"].items():
        types = {}
        for r in v["records"]:
            types[r["type"]] = types.get(r["type"], 0) + 1
        print("case", k, v["name"], "record types:", types)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
