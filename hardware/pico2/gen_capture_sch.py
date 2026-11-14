#!/usr/bin/env python3
"""Schéma d'étude de l'acquisition seule. Ne produit aucun dossier de fabrication.

Les contacts BA restent sans empreinte jusqu'à vérification mécanique.
L'étage ICSP est volontairement absent : voir README, blocage MCLR/NCP803.
"""
from pathlib import Path
import json
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kicad"))
import schematic as s

s.NAME = "pico2-capture-draft"
s.OUT = str(Path(__file__).resolve().parent)
s.U = lambda name: str(uuid.uuid5(uuid.NAMESPACE_URL, "essensys/pico2-capture/" + name))
s.ROOT = s.U("root")
RES = "Resistor_SMD:R_0603_1608Metric"
CAP = "Capacitor_SMD:C_0603_1608Metric"
BUF = "Package_TO_SOT_SMD:SOT-23-6"


def terminal(point, net, direction="left", length=5.08):
    net = "GND" if net == "0V" else net
    x, y = point
    dx, dy = {"left": (-length, 0), "right": (length, 0),
              "up": (0, -length), "down": (0, length)}[direction]
    end = (round(x + dx, 3), round(y + dy, 3))
    s.wire(point, end)
    s.label(net, *end)
    s.items[-1][3] = s.fx(j=["right" if direction == "left" else "left", "bottom"])


s.text("ETUDE ANTERIEURE — MODULE PICO / PIO — VOIR ADR-001", 12.7, 15.24, 2.2, bold=True)
s.text("NON FABRICABLE : ICSP absent ; empreintes BA et qualification électrique en attente.\n"
       "USB uniquement pour l'alimentation. +15 V limité à la traversée J1/J2. Aucune pull-up sur les signaux.",
       12.7, 25.4, 1.4)

for ref, y in (("J1", 40.64), ("J2", 60.96)):
    x = 40.64
    pins = s.sym("Connector_Generic:Conn_02x02_Odd_Even", ref, "BA " + ref, "", x, y,
                 extra={"Note": "WR-MPC3 2x2 : empreinte mécanique à confirmer avant PCB"},
                 ref_at=(x - 2.54, y - 5.08), val_at=(x - 2.54, y + 10.16))
    for pin, net in {"1": "SDA_BUS", "2": "SCL_BUS", "3": "0V", "4": "+15V_PASS"}.items():
        terminal(pins[pin], net, "left" if int(pin) % 2 else "right")

idc = s.sym("Connector_Generic:Conn_02x07_Odd_Even", "J3", "IDC14 FC14P",
            "Connector_IDC:IDC-Header_2x07_P2.54mm_Vertical", 45.72, 152.4,
            ref_at=(40.64, 134.62), val_at=(35.56, 172.72),
            extra={"Note": "Nappe femelle-femelle 1 m ; vérifier détrompeur et continuité"})
for pin in range(1, 15):
    terminal(idc[str(pin)], f"CH{pin}_IDC" if pin <= 8 else "0V", "left" if pin % 2 else "right")
s.text("IDC : 1..8 signaux, 9..14 masses.\nAucune tension d'alimentation sur la nappe.\nPas de raccordement direct à l'analyseur 2x5.", 12.7, 187.96, 1.27)

for ch, net in ((1, "SCL_BUS"), (2, "SDA_BUS")):
    y = 81.28 + (ch - 1) * 25.4
    selector = s.sym("Jumper:Jumper_3_Open", f"JP{ch}", "BUS / IDC",
                     "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
                     63.5, y, ref_at=(60.96, y - 5.08), val_at=(60.96, y + 12.7))
    terminal(selector["1"], net)
    terminal(selector["3"], f"CH{ch}_IDC", "right")
    terminal(selector["2"], f"CH{ch}_SOURCE", "down")

for ch in range(1, 9):
    y = 50.8 + (ch - 1) * 22.86
    r = s.sym("Device:R", f"R{ch}", "1k", RES, 139.7, y, angle=90,
              ref_at=(137.16, y - 3.81), val_at=(137.16, y + 6.35))
    terminal(r["1"], f"CH{ch}_SOURCE" if ch <= 2 else f"CH{ch}_IDC")
    terminal(r["2"], f"CH{ch}_IN", "right")
    pull = s.sym("Device:R", f"R{ch + 8}", "1M", RES, 182.88, y + 2.54,
                 ref_at=(185.42, y), val_at=(185.42, y + 5.08))
    terminal(pull["1"], f"CH{ch}_IN", "up", 2.54)
    terminal(pull["2"], "0V", "down", 2.54)
    unit = 1 if ch % 2 else 2
    u = s.sym("74xGxx:74LVC2G17", f"U{(ch + 1) // 2}", "SN74LVC2G17DBVR", BUF,
              266.7, y, unit=unit, hide_val=unit == 2,
              ref_at=(264.16, y - 5.08), val_at=(256.54, y + 7.62),
              extra={"Manufacturer": "Texas Instruments", "LCSC": "C10429"})
    terminal(u["1" if unit == 1 else "3"], f"CH{ch}_IN")
    terminal(u["6" if unit == 1 else "4"], f"GPIO{ch - 1}", "right")

for pair in range(4):
    y = 62.23 + pair * 45.72
    d = s.sym("Power_Protection:SP0502BAHT", f"D{pair + 1}", "SP0502BAHTG",
              "Package_TO_SOT_SMD:SOT-23", 226.06, y,
              ref_at=(233.68, y - 2.54), val_at=(218.44, y + 15.24),
              extra={"Manufacturer": "Littelfuse", "LCSC": "C207261"})
    # Separate labelled stubs keep the two clamp channels visibly distinct.
    terminal(d["1"], f"CH{pair * 2 + 1}_IN", "up", 2.54)
    terminal(d["2"], f"CH{pair * 2 + 2}_IN", "right", 10.16)
    terminal(d["3"], "0V", "down", 2.54)
    x = 129.54 + pair * 66.04
    power = s.sym("74xGxx:74LVC2G17", f"U{pair + 1}", "SN74LVC2G17DBVR", BUF,
                  x, 233.68, unit=3, hide_val=True,
                  extra={"Manufacturer": "Texas Instruments", "LCSC": "C10429"})
    terminal(power["5"], "+3V3", "up", 2.54)
    terminal(power["2"], "0V", "down", 2.54)
    c = s.sym("Device:C", f"C{pair + 1}", "100n", CAP, x + 25.4, 233.68,
              ref_at=(x + 27.94, 231.14), val_at=(x + 27.94, 236.22))
    terminal(c["1"], "+3V3", "up", 2.54)
    terminal(c["2"], "0V", "down", 2.54)

pico = s.sym("MCU_Module:RaspberryPi_Pico", "A1", "Raspberry Pi Pico 2",
             "Module:RaspberryPi_Pico_Common_Unspecified", 353.06, 116.84,
             ref_at=(342.9, 73.66), val_at=(342.9, 76.2),
             extra={"Note": "Symbole brochage commun Pico/Pico 2 ; module assemblé manuellement"})
gpio_pins = [1, 2, 4, 5, 6, 7, 9, 10]
ground_pins = [3, 8, 13, 18, 23, 28, 38]
used_positions = set()
for pin, point in pico.items():
    n = int(pin)
    if n in gpio_pins:
        terminal(point, f"GPIO{gpio_pins.index(n)}")
    elif n == 36:
        terminal(point, "+3V3", "up")
    elif n in ground_pins:
        if point not in used_positions:
            terminal(point, "0V", "down")
    else:
        s.no_connect(*point)
    used_positions.add(point)
# AGND is already connected inside the module; no analogue circuit uses pin 33.
s.text("GPIO0..7 en entrée uniquement.\nUSB sur le module Pico 2.\nICSP non implémenté sur cette feuille.\nR série / capacité SP0502 à qualifier :\n10 MS/s est une limite logicielle,\npas une bande passante mesurée.", 307.34, 205.74, 1.27)

sch = ["kicad_sch", ["version", "20250114"], ["generator", s.S("eeschema")],
       ["uuid", s.ROOT], ["paper", s.S("A3")],
       ["title_block", ["title", s.S("ETUDE ANTERIEURE — Pico module / capture PIO")],
        ["date", s.S("2026-11-14")], ["rev", s.S("DRAFT-0")],
        ["comment", "1", s.S("Refs #10 — Feature i2c-ba-sniffer-2026-10-009")],
        ["comment", "2", s.S("REMPLACEE PAR ADR-001 RP2350 + FX2 — NON FABRICABLE")]],
       ["lib_symbols"] + s.libsyms] + s.items + [
           ["sheet_instances", ["path", s.S("/"), ["page", s.S("1")]]], ["embedded_fonts", "no"]]
Path(s.OUT, s.NAME + ".kicad_sch").write_text(s.dump(sch) + "\n")
Path(s.OUT, s.NAME + ".kicad_pro").write_text(json.dumps({
    "meta": {"filename": s.NAME + ".kicad_pro", "version": 3},
    "schematic": {}, "sheets": [[s.ROOT, "Capture"]], "text_variables": {},
}, indent=2) + "\n")
print("Schéma d'étude généré — aucun PCB, aucun Gerber")
for filename, kind, libraries, suffix in (
    ("sym-lib-table", "sym", {lid.split(":")[0] for lid in s.pinmap}, ".kicad_sym"),
    ("fp-lib-table", "fp", {"Resistor_SMD", "Capacitor_SMD", "Package_TO_SOT_SMD",
                            "Connector_IDC", "Connector_PinHeader_2.54mm", "Module"}, ".pretty"),
):
    variable = "KICAD10_SYMBOL_DIR" if kind == "sym" else "KICAD10_FOOTPRINT_DIR"
    rows = [f'  (lib (name "{name}")(type "KiCad")(uri "${{{variable}}}/{name}{suffix}")(options "")(descr ""))'
            for name in sorted(libraries)]
    Path(s.OUT, filename).write_text(f"({kind}_lib_table\n  (version 7)\n" + "\n".join(rows) + ")\n")
