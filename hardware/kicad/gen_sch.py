#!/usr/bin/env python3
"""Génère le schéma KiCad (outils KiCad 10) de la sonde passive (``sonde-i2c-passive.kicad_sch``).

Feature i2c-ba-sniffer-2026-10-009 (essensys-hub/essensys-feature-lifecycle#29), tâche 5.2.
Réalisation sur plaque à pastilles (tâche 5.3) : pas de PCB.

Usage : ``python3 hardware/kicad/gen_sch.py`` (KiCad 10 installé ; chemin des symboles
dans ``KICAD9_SYMBOL_DIR`` ou emplacement macOS par défaut). Utilitaires S-expression
repris de essensys-i2c-etoile-0v/scripts/gen_sch.py.
"""
from schematic import *  # Primitives sans génération implicite.

G1 = 2.54
Y_SCL, Y_SDA = 50.8, 76.2
RES = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
MPC = ""  # pas d'empreinte : boîtier câble WR-MPC3 serti, fils soudés sur la plaque à pastilles

# --- J1 : câble vers le BA ---
j1 = sym("Connector_Generic:Conn_02x02_Odd_Even", "J1", "Câble vers BA J1/J2", MPC, 30.48, 63.5,
         extra={"Manufacturer": "Würth Elektronik", "MPN": "WR-MPC3 2x2, boîtier femelle câble (à confirmer, tâche 5.1)",
                "Note": "Boîtier câble ; seuls les contacts 1, 2, 3 sont sertis, la position 4 (+15 V) reste vide ; fils soudés sur la plaque"},
         ref_at=(27.94, 58.42), val_at=(30.48, 71.12))
no_connect(*j1["4"])
wire(j1["2"], (43.18, 63.5), (43.18, Y_SCL))
wire(j1["1"], (17.78, 63.5), (17.78, Y_SDA))
wire(j1["3"], (22.86, 66.04), (22.86, 68.58)); gnd(22.86, 68.58)

# --- résistances série ---
r2 = sym("Device:R", "R2", "1k", RES, 55.88, Y_SCL, angle=90, ref_at=(54.61, Y_SCL - 3.81), val_at=(54.61, Y_SCL + 5.08),
         extra={"Note": "Série SCL"})
r1 = sym("Device:R", "R1", "1k", RES, 55.88, Y_SDA, angle=90, ref_at=(54.61, Y_SDA - 3.81), val_at=(54.61, Y_SDA + 5.08),
         extra={"Note": "Série SDA"})
wire((43.18, Y_SCL), r2["1"])
wire((17.78, Y_SDA), r1["1"])
label("SCL_BUS", 44.45, Y_SCL); label("SDA_BUS", 30.48, Y_SDA)

# --- rappels au 0 V ---
r4 = sym("Device:R", "R4", "1M", RES, 68.58, 58.42, ref_at=(70.61, 57.15), val_at=(70.61, 60.96), extra={"Note": "Rappel SCL au 0 V"})
r3 = sym("Device:R", "R3", "1M", RES, 68.58, 83.82, ref_at=(70.61, 82.55), val_at=(70.61, 86.36), extra={"Note": "Rappel SDA au 0 V"})
wire((68.58, Y_SCL), r4["1"]); wire(r4["2"], (68.58, 64.77)); gnd(68.58, 64.77)
wire((68.58, Y_SDA), r3["1"]); wire(r3["2"], (68.58, 90.17)); gnd(68.58, 90.17)

# --- protection ---
d1 = sym("Power_Protection:SP0502BAHT", "D1", "SP0502BAHT", "Package_TO_SOT_SMD:SOT-23", 81.28, 88.9,
         extra={"Manufacturer": "Littelfuse", "MPN": "SP0502BAHT", "Note": "Sur adaptateur SOT-23 vers SIP3"},
         ref_at=(86.36, 87.63), val_at=(86.36, 91.44))
wire(d1["1"], (78.74, Y_SDA)); wire(d1["2"], (83.82, Y_SCL)); wire(d1["3"], (81.28, 96.52)); gnd(81.28, 96.52)

# --- tampon ---
U1FP = "Package_TO_SOT_SMD:SOT-363_SC-70-6"
U1X = {"Manufacturer": "Nexperia / TI", "MPN": "74LVC2G17GW / SN74LVC2G17DCK",
       "Note": "Entrées tolérantes 5,5 V (Ioff) sous VCC = 3,3 V ; sur adaptateur SC-70 vers DIP6"}
ua = sym("74xGxx:74LVC2G17", "U1", "74LVC2G17", U1FP, 106.68, Y_SCL, unit=1, extra=U1X, ref_at=(104.14, 44.45), val_at=(104.14, 57.15))
ub = sym("74xGxx:74LVC2G17", "U1", "74LVC2G17", U1FP, 106.68, Y_SDA, unit=2, extra=U1X, ref_at=(104.14, 69.85), val_at=(104.14, 82.55), hide_val=True)
uc = sym("74xGxx:74LVC2G17", "U1", "74LVC2G17", U1FP, 139.7, 101.6, unit=3, extra=U1X, ref_at=(145.8, 99.06), val_at=(145.8, 104.14), hide_val=True)

# rangées SCL / SDA (segments entre jonctions)
wire(r2["2"], (68.58, Y_SCL), (83.82, Y_SCL), ua["1"])
wire(r1["2"], (68.58, Y_SDA), (78.74, Y_SDA), ub["3"])
for jx, jy in ((68.58, Y_SCL), (83.82, Y_SCL), (68.58, Y_SDA), (78.74, Y_SDA)):
    junction(jx, jy)
label("SCL_IN", 86.36, Y_SCL); label("SDA_IN", 86.36, Y_SDA)

# --- alimentation de U1 ---
wire(uc["5"], (139.7, 88.9)); vcc(139.7, 88.9); flag(134.62, 88.9, 1); wire((134.62, 88.9), (139.7, 88.9))
wire(uc["2"], (139.7, 114.3)); gnd(139.7, 114.3); flag(134.62, 114.3, 2); wire((134.62, 114.3), (139.7, 114.3))
c1 = sym("Device:C", "C1", "100n", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm", 157.48, 101.6,
         ref_at=(160.02, 100.33), val_at=(160.02, 104.14), extra={"Note": "Découplage au plus près de U1"})
wire(c1["1"], (157.48, 95.25)); vcc(157.48, 95.25)
wire(c1["2"], (157.48, 107.95)); gnd(157.48, 107.95)

# --- J2 vers l'analyseur ---
j2 = sym("Connector_Generic:Conn_01x04", "J2", "Vers analyseur FX2", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
         175.26, 60.96, extra={"Note": "1 +3,3 V, 2 SCL vers D0, 3 SDA vers D1, 4 0 V (GND de l'analyseur et du Pi)"},
         ref_at=(173.99, 53.34), val_at=(177.8, 68.58))
wire(ua["6"], (160.02, Y_SCL), (160.02, 60.96), j2["2"])
wire(ub["4"], (162.56, Y_SDA), (162.56, 63.5), j2["3"])
wire(j2["1"], (165.1, 58.42), (165.1, 55.88)); vcc(165.1, 55.88)
wire(j2["4"], (167.64, 66.04), (167.64, 68.58)); gnd(167.64, 68.58)
label("SCL_OUT", 121.92, Y_SCL); label("SDA_OUT", 121.92, Y_SDA)

# --- textes ---
text("SONDE I2C PASSIVE — espion du bus BP / BA (lecture seule)", 12.7, 25.4, 2.0, n="titre", bold=True)
text("3 fils côté bus (SDA, SCL, 0 V) ; position 4 (+15 V) du connecteur VIDE. Aucune pull-up, rien n'est alimenté par le bus.\n"
     "Le 0 V de la sonde est le 0 V de l'armoire : analyseur et Raspberry Pi sur batterie, jamais reliés au PE.", 12.7, 31.75, 1.4, n="regles")
text("CÔTÉ BUS\nBA J1/J2 (WR-MPC3)\n1 SDA · 2 SCL · 3 0 V · 4 +15 V", 7.62, 41.91, 1.27, n="cotebus", bold=False)
text("PROTECTION ET TAMPON", 76.2, 41.91, 1.27, n="blocprot", bold=True)
text("CÔTÉ ANALYSEUR\nJ2 : 1 +3,3 V · 2 SCL→D0\n3 SDA→D1 · 4 0 V", 160.02, 41.91, 1.27, n="coteana", bold=False)
text("Alimentation de U1 : +3,3 V de J2 (analyseur, ou broche 1 du GPIO du Pi).\n"
     "0 V commun : J2-4, GND de l'analyseur et du Pi (aussi relié par le câble USB).", 86.36, 127.0, 1.27, n="alim")

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
fplibs = sorted({"Resistor_THT", "Package_TO_SOT_SMD", "Capacitor_THT", "Connector_PinHeader_2.54mm"})
open(os.path.join(OUT, "fp-lib-table"), "w").write(
    "(fp_lib_table\n\t(version 7)\n" + "".join(row % (lname, "${KICAD9_FOOTPRINT_DIR}/%s.pretty" % lname, "") for lname in fplibs) + ")\n")
pro = {"meta": {"filename": NAME + ".kicad_pro", "version": 3}, "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
       "sheets": [[ROOT, "Root"]], "text_variables": {}}
import json  # noqa: E402

open(os.path.join(OUT, NAME + ".kicad_pro"), "w").write(json.dumps(pro, indent=2) + "\n")
print("ok", NAME)
