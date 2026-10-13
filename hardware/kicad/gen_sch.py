#!/usr/bin/env python3
"""Génère le schéma KiCad 9 de la sonde passive (``sonde-i2c-passive.kicad_sch``).

Feature i2c-ba-sniffer-2026-10-009 (essensys-hub/essensys-feature-lifecycle#29), tâche 5.2.
Réalisation sur plaque à pastilles (tâche 5.3) : pas de PCB.

Usage : ``python3 hardware/kicad/gen_sch.py`` (KiCad 9 installé ; chemin des symboles
dans ``KICAD9_SYMBOL_DIR`` ou emplacement macOS par défaut). Utilitaires S-expression
repris de essensys-i2c-etoile-0v/scripts/gen_sch.py.
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
DIRS = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}


def place(lid, ref, val, fp, x, y, nets, extra=None, unit=1, inbom=True):
    """nets : broche -> net ; un fil de 2,54 mm puis un label par broche ('NC' = drapeau no-connect)."""
    need(lid)
    hidden = ref.startswith("#")
    props = [["property", S("Reference"), S(ref), ["at", f(x + G), f(y - 5.08), "0"], fx(j=["left"], hide=hidden)],
             ["property", S("Value"), S(val), ["at", f(x + G), f(y + 6.35), "0"], fx(j=["left"], hide=hidden)],
             ["property", S("Footprint"), S(fp), ["at", f(x), f(y), "0"], fx(hide=True)],
             ["property", S("Datasheet"), S(""), ["at", f(x), f(y), "0"], fx(hide=True)]]
    for k, v in (extra or {}).items():
        props.append(["property", S(k), S(v), ["at", f(x), f(y), "0"], fx(hide=True)])
    upins = [p for p, d in pinmap[lid].items() if d[3] in (0, unit)]
    items.append(["symbol", ["lib_id", S(lid)], ["at", f(x), f(y), "0"], ["unit", str(unit)],
                  ["exclude_from_sim", "no"], ["in_bom", "yes" if inbom else "no"], ["on_board", "yes"], ["dnp", "no"],
                  ["uuid", U("sym/%s/%d" % (ref, unit))]] + props +
                 [["pin", S(p), ["uuid", U("pin/%s/%s" % (ref, p))]] for p in upins] +
                 [["instances", ["project", S(NAME), ["path", S("/" + ROOT), ["reference", S(ref)], ["unit", str(unit)]]]]])
    for p, net in nets.items():
        if p not in upins:
            continue
        px, py, a, _ = pinmap[lid][p]
        sx, sy = x + px, y - py
        if net == "NC":
            items.append(["no_connect", ["at", f(sx), f(sy)], ["uuid", U("nc/%s/%s" % (ref, p))]])
            continue
        d = DIRS[a]
        ex, ey = sx + d[0] * G, sy + d[1] * G
        items.append(["wire", ["pts", ["xy", f(sx), f(sy)], ["xy", f(ex), f(ey)]],
                      ["stroke", ["width", "0"], ["type", "default"]], ["uuid", U("w/%s/%s" % (ref, p))]])
        ang, just = {(-1, 0): ("180", ["right", "bottom"]), (1, 0): ("0", ["left", "bottom"]),
                     (0, 1): ("270", ["right", "bottom"]), (0, -1): ("90", ["left", "bottom"])}[d]
        items.append(["label", S(net), ["at", f(ex), f(ey), ang], fx(j=just), ["uuid", U("l/%s/%s" % (ref, p))]])


def text(t, x, y, size=1.27, n=None, bold=False):
    font = ["font", ["size", f(size), f(size)]] + ([["bold", "yes"]] if bold else [])
    items.append(["text", S(t), ["exclude_from_sim", "no"], ["at", f(x), f(y), "0"],
                  ["effects", font, ["justify", "left", "bottom"]], ["uuid", U("t/" + (n or t[:40]))]])


# ================= Sonde =================
MPC = "Connector_Molex:Molex_Micro-Fit_3.0_43045-0412_2x02_P3.00mm_Vertical"  # boîtier câble ; sur la plaque, fils soudés
place("Connector_Generic:Conn_02x02_Odd_Even", "J1", "Vers BA J1/J2 (WR-MPC3 2x2, position 4 VIDE)", MPC, 30.48, 66.04,
      {"1": "SDA_BUS", "2": "SCL_BUS", "3": "0V", "4": "NC"},
      {"Manufacturer": "Würth Elektronik", "MPN": "WR-MPC3 2x2 boîtier femelle câble (à confirmer, tâche 5.1)",
       "Note": "Seuls les contacts 1, 2, 3 sont sertis ; la position 4 (+15 V) reste vide"})
place("Device:R", "R1", "1k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", 76.2, 50.8,
      {"1": "SDA_BUS", "2": "SDA_IN"}, {"Note": "Résistance série : limite le courant en cas d'erreur"})
place("Device:R", "R2", "1k", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", 76.2, 96.52,
      {"1": "SCL_BUS", "2": "SCL_IN"}, {"Note": "Résistance série : limite le courant en cas d'erreur"})
place("Device:R", "R3", "1M", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", 101.6, 50.8,
      {"1": "SDA_IN", "2": "0V"}, {"Note": "Rappel au 0 V si la sonde est débranchée (5 µA sous 5 V, négligeable)"})
place("Device:R", "R4", "1M", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", 101.6, 96.52,
      {"1": "SCL_IN", "2": "0V"}, {"Note": "Rappel au 0 V si la sonde est débranchée"})
place("Power_Protection:SP0502BAHT", "D1", "SP0502BAHT", "Package_TO_SOT_SMD:SOT-23", 127.0, 73.66,
      {"1": "SDA_IN", "2": "SCL_IN", "3": "0V"},
      {"Manufacturer": "Littelfuse", "MPN": "SP0502BAHT", "Note": "TVS 2 voies, sur adaptateur SOT-23 vers DIP"})
U1FP = "Package_TO_SOT_SMD:SOT-363_SC-70-6"
U1X = {"Manufacturer": "Nexperia / TI", "MPN": "74LVC2G17GW / SN74LVC2G17DCK",
       "Note": "Entrées tolérantes 5,5 V sous VCC = 3,3 V ; sur adaptateur SC-70 vers DIP"}
place("74xGxx:74LVC2G17", "U1", "74LVC2G17", U1FP, 160.02, 50.8, {"1": "SCL_IN", "6": "SCL_OUT"}, U1X, unit=1)
place("74xGxx:74LVC2G17", "U1", "74LVC2G17", U1FP, 160.02, 96.52, {"3": "SDA_IN", "4": "SDA_OUT"}, U1X, unit=2)
place("74xGxx:74LVC2G17", "U1", "74LVC2G17", U1FP, 195.58, 73.66, {"5": "+3V3", "2": "0V"}, U1X, unit=3)
place("Device:C", "C1", "100n", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm", 220.98, 73.66,
      {"1": "+3V3", "2": "0V"}, {"Note": "Découplage au plus près de U1"})
place("Connector_Generic:Conn_01x04", "J2", "Vers analyseur logique FX2", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
      254.0, 73.66, {"1": "0V", "2": "SCL_OUT", "3": "SDA_OUT", "4": "+3V3"},
      {"Note": "1 GND, 2 voie D0 (SCL), 3 voie D1 (SDA), 4 +3,3 V de l'analyseur ou broche 1 du GPIO du Raspberry Pi"})
place("power:PWR_FLAG", "#FLG01", "PWR_FLAG", "", 241.3, 101.6, {"1": "+3V3"}, inbom=False)
place("power:PWR_FLAG", "#FLG02", "PWR_FLAG", "", 30.48, 101.6, {"1": "0V"}, inbom=False)

text("SONDE I2C PASSIVE — espion du bus BP↔BA Essensys (lecture seule)", 25.4, 25.4, 2.0, n="titre", bold=True)
text("Côté bus : 3 fils seulement (SDA, SCL, 0 V). Position 4 (+15 V) du connecteur VIDE.\n"
     "Aucune pull-up, aucune alimentation prélevée sur le bus. 1 kΩ série + TVS 5,5 V + tampon 5 V-tolérant.\n"
     "Le 0 V de la sonde n'est JAMAIS relié au PE : analyseur et hôte sur batterie (ou isolateur USB).",
     25.4, 33.02, 1.4, n="regles")
text("Brochage WR-MPC3 du BA : 1 SDA, 2 SCL, 3 0 V, 4 +15 V", 15.24, 81.28, 1.27, n="brochage")

sch = ["kicad_sch", ["version", "20250114"], ["generator", S("eeschema")], ["generator_version", S("9.0")],
       ["uuid", ROOT], ["paper", S("A4")],
       ["title_block", ["title", S("Sonde I2C passive (espion BP↔BA)")], ["date", S("2026-10-13")], ["rev", S("A")],
        ["company", S("Essensys – essensys-i2c-ba-sniffer")],
        ["comment", "1", S("Feature: i2c-ba-sniffer-2026-10-009 – Refs essensys-hub/essensys-feature-lifecycle#29")],
        ["comment", "2", S("Réalisation sur plaque à pastilles (pas de PCB) – tâches 5.2 / 5.3")],
        ["comment", "3", S("Strictement passive : jamais d'émission, jamais de +15 V, 0 V jamais relié au PE")]],
       ["lib_symbols"] + libsyms] + items + [["sheet_instances", ["path", S("/"), ["page", S("1")]]], ["embedded_fonts", "no"]]
open(os.path.join(OUT, NAME + ".kicad_sch"), "w").write(dump(sch) + "\n")

symlibs = sorted({lid.split(":")[0] for lid in pinmap})
row = '\t(lib (name "%s")(type "KiCad")(uri "%s")(options "")(descr "%s"))\n'
open(os.path.join(OUT, "sym-lib-table"), "w").write(
    "(sym_lib_table\n\t(version 7)\n" + "".join(row % (lname, "${KICAD9_SYMBOL_DIR}/%s.kicad_sym" % lname, "") for lname in symlibs) + ")\n")
fplibs = sorted({"Connector_Molex", "Resistor_THT", "Package_TO_SOT_SMD", "Capacitor_THT", "Connector_PinHeader_2.54mm"})
open(os.path.join(OUT, "fp-lib-table"), "w").write(
    "(fp_lib_table\n\t(version 7)\n" + "".join(row % (lname, "${KICAD9_FOOTPRINT_DIR}/%s.pretty" % lname, "") for lname in fplibs) + ")\n")
pro = {"meta": {"filename": NAME + ".kicad_pro", "version": 3}, "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
       "sheets": [[ROOT, "Root"]], "text_variables": {}}
import json  # noqa: E402

open(os.path.join(OUT, NAME + ".kicad_pro"), "w").write(json.dumps(pro, indent=2) + "\n")
print("ok", NAME)
