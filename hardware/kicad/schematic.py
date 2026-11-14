"""Primitives KiCad partagées par les générateurs de schémas du dépôt.

La géométrie reste déterministe (UUID5). Aucune écriture lors de l’import.
Les générateurs configurent NAME, ROOT, OUT et U avant de placer les symboles.
"""
import copy
import os
import uuid

KSYM = os.environ.get("KICAD9_SYMBOL_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols") + "/"
OUT = os.path.dirname(os.path.abspath(__file__))
NAME = "sonde-i2c-passive"
U = lambda s: str(uuid.uuid5(uuid.NAMESPACE_URL, "essensys-i2c-ba-sniffer/" + s))  # noqa: E731
ROOT = U("root")
G = 2.54


# ---------- S-expression ----------
def tok(s):
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in "()":
            yield c
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while s[j] != '"':
                if s[j] == "\\":
                    buf.append(s[j:j + 2])
                    j += 2
                else:
                    buf.append(s[j])
                    j += 1
            yield ("S", "".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in "()":
                j += 1
            yield s[i:j]
            i = j


def parse(s):
    st = [[]]
    for t in tok(s):
        if t == "(":
            st.append([])
        elif t == ")":
            x = st.pop()
            st[-1].append(x)
        else:
            st[-1].append(t)
    return st[0]


def dump(x, ind=0):
    if isinstance(x, tuple):
        return '"' + x[1] + '"'
    if isinstance(x, str):
        return x
    if all(not isinstance(e, list) for e in x):
        return "(" + " ".join(dump(e) for e in x) + ")"
    pad = "\t" * (ind + 1)
    return "(" + dump(x[0]) + "".join("\n" + pad + dump(e, ind + 1) for e in x[1:]) + "\n" + "\t" * ind + ")"


def S(v):
    return ("S", v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n"))


def f(v):
    return ("%.3f" % v).rstrip("0").rstrip(".")


_libs = {}


def lib(name):
    if name not in _libs:
        _libs[name] = parse(open(KSYM + name + ".kicad_sym").read())[0]
    return _libs[name]


def find_sym(libname, sym):
    for e in lib(libname):
        if isinstance(e, list) and e[0] == "symbol" and e[1][1] == sym:
            return copy.deepcopy(e)
    raise KeyError(sym)


def flat_sym(libname, sym):
    s = find_sym(libname, sym)
    ext = [e for e in s if isinstance(e, list) and e[0] == "extends"]
    if not ext:
        return s
    parent = flat_sym(libname, ext[0][1][1])
    pname = parent[1][1]
    parent[1] = S(sym)
    childprops = {e[1][1]: e for e in s if isinstance(e, list) and e[0] == "property"}
    for i, e in enumerate(parent):
        if isinstance(e, list) and e[0] == "property" and e[1][1] in childprops:
            parent[i] = childprops[e[1][1]]
        if isinstance(e, list) and e[0] == "symbol":
            e[1] = S(e[1][1].replace(pname, sym, 1))
    return parent


def pins_of(sym):
    """num -> (x, y, angle, unit) ; ignore la représentation De Morgan (style 2)."""
    res = {}

    def walk(x, unit):
        for e in x:
            if isinstance(e, list):
                if e[0] == "symbol" and isinstance(e[1], tuple):
                    parts = e[1][1].rsplit("_", 2)
                    if len(parts) == 3 and parts[2] == "2":
                        continue
                    walk(e, int(parts[1]) if len(parts) == 3 else unit)
                elif e[0] == "pin":
                    at = [a for a in e if isinstance(a, list) and a[0] == "at"][0]
                    num = [a for a in e if isinstance(a, list) and a[0] == "number"][0][1][1]
                    if num not in res:
                        res[num] = (float(at[1]), float(at[2]), int(float(at[3])), unit)
                else:
                    walk(e, unit)

    walk(sym, 0)
    return res


def fx(size=1.27, hide=False, j=None):
    e = ["effects", ["font", ["size", f(size), f(size)]]]
    if j:
        e.append(["justify"] + j)
    if hide:
        e.append(["hide", "yes"])
    return e


libsyms, pinmap = [], {}


def need(lid):
    if lid in pinmap:
        return
    lname, sname = lid.split(":")
    sy = flat_sym(lname, sname)
    pinmap[lid] = pins_of(sy)
    sy[1] = S(lid)
    libsyms.append(sy)


items = []


def text(t, x, y, size=1.27, n=None, bold=False):
    font = ["font", ["size", f(size), f(size)]] + ([["bold", "yes"]] if bold else [])
    items.append(["text", S(t), ["exclude_from_sim", "no"], ["at", f(x), f(y), "0"],
                  ["effects", font, ["justify", "left", "bottom"]], ["uuid", U("t/" + (n or t[:40]))]])


# ================= Sonde (schéma câblé, gauche → droite) =================
# Rangée du haut : SCL ; rangée du bas : SDA. Masse et +3,3 V par symboles locaux.
ROT = {0: lambda dx, dy: (dx, dy), 90: lambda dx, dy: (dy, -dx), 180: lambda dx, dy: (-dx, -dy), 270: lambda dx, dy: (-dy, dx)}


def sym(lid, ref, val, fp, x, y, angle=0, unit=1, extra=None, inbom=True, ref_at=None, val_at=None, hide_val=False):
    """Place un symbole et retourne {broche: (x, y)} en coordonnées feuille."""
    need(lid)
    hidden = ref.startswith("#")
    ref_at = ref_at or (x + 2.54, y - 3.81)
    val_at = val_at or (x + 2.54, y + 3.81)
    fa = str((360 - angle) % 360) if angle else "0"  # textes des champs toujours horizontaux
    props = [["property", S("Reference"), S(ref), ["at", f(ref_at[0]), f(ref_at[1]), fa], fx(j=["left"], hide=hidden)],
             ["property", S("Value"), S(val), ["at", f(val_at[0]), f(val_at[1]), fa], fx(j=["left"], hide=hide_val)],
             ["property", S("Footprint"), S(fp), ["at", f(x), f(y), "0"], fx(hide=True)],
             ["property", S("Datasheet"), S(""), ["at", f(x), f(y), "0"], fx(hide=True)]]
    for k, v in (extra or {}).items():
        props.append(["property", S(k), S(v), ["at", f(x), f(y), "0"], fx(hide=True)])
    upins = [p for p, d in pinmap[lid].items() if d[3] in (0, unit)]
    items.append(["symbol", ["lib_id", S(lid)], ["at", f(x), f(y), str(angle)], ["unit", str(unit)],
                  ["exclude_from_sim", "no"], ["in_bom", "yes" if inbom else "no"], ["on_board", "yes" if inbom else "no"], ["dnp", "no"],
                  ["uuid", U("sym/%s/%d" % (ref, unit))]] + props +
                 [["pin", S(p), ["uuid", U("pin/%s/%s" % (ref, p))]] for p in upins] +
                 [["instances", ["project", S(NAME), ["path", S("/" + ROOT), ["reference", S(ref)], ["unit", str(unit)]]]]])
    out = {}
    for p in upins:
        px, py, _, _ = pinmap[lid][p]
        dx, dy = ROT[angle](px, -py)
        out[p] = (round(x + dx, 3), round(y + dy, 3))
    return out


_w = [0]


def wire(*pts):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        _w[0] += 1
        items.append(["wire", ["pts", ["xy", f(x1), f(y1)], ["xy", f(x2), f(y2)]],
                      ["stroke", ["width", "0"], ["type", "default"]], ["uuid", U("wire/%d" % _w[0])]])


def junction(x, y):
    items.append(["junction", ["at", f(x), f(y)], ["diameter", "0"], ["color", "0", "0", "0", "0"], ["uuid", U("j/%s/%s" % (x, y))]])


def no_connect(x, y):
    items.append(["no_connect", ["at", f(x), f(y)], ["uuid", U("nc/%s/%s" % (x, y))]])


def label(net, x, y, angle=0):
    items.append(["label", S(net), ["at", f(x), f(y), str(angle)], fx(j=["left", "bottom"]), ["uuid", U("lab/%s/%s/%s" % (net, x, y))]])


_p = [0]


def gnd(x, y):
    _p[0] += 1
    sym("power:GND", "#PWR%02d" % _p[0], "0V", "", x, y, inbom=False, ref_at=(x, y + 6.35), val_at=(x - 1.27, y + 4.45))


def vcc(x, y):
    _p[0] += 1
    sym("power:+3V3", "#PWR%02d" % _p[0], "+3V3", "", x, y, inbom=False, ref_at=(x, y - 6.35), val_at=(x - 1.27, y - 3.81))


def flag(x, y, n):
    sym("power:PWR_FLAG", "#FLG%02d" % n, "PWR_FLAG", "", x, y, inbom=False, hide_val=True)


