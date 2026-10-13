#!/usr/bin/env python3
"""Génère le câblage Fritzing de la sonde passive : ``sonde-i2c-passive.fzz`` (vue platine).

Feature i2c-ba-sniffer-2026-10-009 (essensys-hub/essensys-feature-lifecycle#29), tâche 5.4.

Chaîne représentée : connecteur du BA → sonde sur plaque à pastilles
(R1-R4, D1 SP0502BAHT sur adaptateur SIP, U1 74LVC2G17 sur adaptateur DIP6, C1)
→ J2 → analyseur logique FX2 → Raspberry Pi sur batterie.

Les fils sont placés sur les connecteurs réels des pièces : leur position est lue
dans les SVG des pièces Fritzing (90 px par pouce en vue platine). Les pièces
génériques (connecteurs, DIP, SIP), créées à la volée par Fritzing, sont copiées
dans ``partfactory/`` (générées par Fritzing 1.0, licence CC-BY-SA).

Usage : ``python3 hardware/fritzing/gen_fzz.py`` puis, pour les exports :
``/Applications/Fritzing.app/Contents/MacOS/Fritzing -svg hardware/fritzing``.
"""

from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
FZ_PARTS = os.environ.get("FRITZING_PARTS", "/Applications/Fritzing.app/Contents/Resources/fritzing-parts")
NAME = "sonde-i2c-passive"
DPI = 90.0


# ---------- géométrie des connecteurs ----------
def _units(value: str) -> float:
    m = re.fullmatch(r"\s*([\d.]+)\s*(in|mm|px|pt)?\s*", value)
    num, unit = float(m[1]), m[2] or "px"
    return num * {"in": DPI, "mm": DPI / 25.4, "px": 1.0, "pt": DPI / 72}[unit]


def _transform(attr: str | None):
    m11, m12, m21, m22, dx, dy = 1, 0, 0, 1, 0, 0
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", attr or ""):
        v = [float(a) for a in re.split(r"[ ,]+", args.strip()) if a]
        if name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        elif name == "matrix":
            t = tuple(v)
        else:
            continue
        a, b, c, d, e, f = t
        m11, m12, m21, m22, dx, dy = (m11 * a + m21 * b, m12 * a + m22 * b, m11 * c + m21 * d,
                                      m12 * c + m22 * d, m11 * e + m21 * f + dx, m12 * e + m22 * f + dy)
    return (m11, m12, m21, m22, dx, dy)


def _apply(t, x, y):
    m11, m12, m21, m22, dx, dy = t
    return (m11 * x + m21 * y + dx, m12 * x + m22 * y + dy)


def connector_points(svg_path: str, ids: list[str]) -> dict[str, tuple[float, float]]:
    """Centre (ou extrémité extérieure d'une patte) de chaque élément, en px de vue platine."""
    root = ET.parse(svg_path).getroot()
    vb = [float(v) for v in re.split(r"[ ,]+", root.get("viewBox").strip())]
    sx = _units(root.get("width")) / vb[2]
    sy = _units(root.get("height")) / vb[3]
    found: dict[str, tuple[float, float]] = {}

    def walk(el, t):
        t = _compose(t, _transform(el.get("transform")))
        eid = el.get("id")
        if eid in ids:
            tag = el.tag.split("}")[-1]
            if tag == "line":
                x, y = float(el.get("x1")), float(el.get("y1"))
            elif tag == "circle":
                x, y = float(el.get("cx")), float(el.get("cy"))
            elif tag == "rect":
                x = float(el.get("x", 0)) + float(el.get("width")) / 2
                y = float(el.get("y", 0)) + float(el.get("height")) / 2
            else:
                nums = [float(n) for n in re.findall(r"-?[\d.]+", el.get("d") or el.get("points") or "0 0")]
                xs, ys = nums[0::2], nums[1::2]
                x, y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            px, py = _apply(t, x, y)
            found[eid] = ((px - vb[0]) * sx, (py - vb[1]) * sy)
        for child in el:
            walk(child, t)

    walk(root, (1, 0, 0, 1, 0, 0))
    missing = set(ids) - set(found)
    if missing:
        raise KeyError(f"{os.path.basename(svg_path)} : {sorted(missing)}")
    return found


def _compose(a, b):
    a11, a12, a21, a22, adx, ady = a
    b11, b12, b21, b22, bdx, bdy = b
    return (a11 * b11 + a21 * b12, a12 * b11 + a22 * b12, a11 * b21 + a21 * b22,
            a12 * b21 + a22 * b22, a11 * bdx + a21 * bdy + adx, a12 * bdx + a22 * bdy + ady)


def part_info(fzp: str):
    """(fichier SVG platine, {connecteur: id SVG à utiliser}) d'une pièce."""
    text = open(fzp, encoding="utf-8").read()
    bb = re.search(r"<breadboardView[^>]*>.*?image=\"([^\"]+)\"", text, re.S)[1]
    conns = {}
    for cid, body in re.findall(r'<connector [^>]*id="(connector\d+)"[^>]*>(.*?)</connector>', text, re.S):
        p = re.search(r'<p [^>]*layer="breadboard(?:breadboard)?"[^>]*/>', body)
        leg = re.search(r'legId="([^"]+)"', p[0]) if p else None
        svg = re.search(r'svgId="([^"]+)"', p[0]) if p else None
        conns[cid] = (leg or svg)[1]
    local = os.path.join(HERE, "partfactory", os.path.basename(bb))
    svg = local if os.path.exists(local) else os.path.join(FZ_PARTS, "svg", "core", bb)
    return svg, conns


# ---------- croquis ----------
CORE = os.path.join(FZ_PARTS, "core")
PF = os.path.join(HERE, "partfactory")
PARTS = {
    # titre: (moduleIdRef, fzp, x, y, propriétés) — positions en px de vue platine (90 px/pouce)
    "BA": ("generic_male_pin_header_4_100mil", f"{PF}/generic_male_pin_header_4_100mil.fzp", 0, 99, {}),
    "R1": ("ResistorModuleID", f"{CORE}/resistor.fzp", 54, 45, {"resistance": "1kΩ", "pin spacing": "400 mil"}),
    "R2": ("ResistorModuleID", f"{CORE}/resistor.fzp", 54, 153, {"resistance": "1kΩ", "pin spacing": "400 mil"}),
    "R3": ("ResistorModuleID", f"{CORE}/resistor.fzp", 126, 18, {"resistance": "1MΩ", "pin spacing": "400 mil"}),
    "R4": ("ResistorModuleID", f"{CORE}/resistor.fzp", 126, 180, {"resistance": "1MΩ", "pin spacing": "400 mil"}),
    "D1": ("generic_sip_3_100mil", f"{PF}/generic_sip_3_100mil.fzp", 207, 117, {"chip label": "SP0502BAHT"}),
    "U1": ("generic_ic_dip_6_300mil", f"{PF}/generic_ic_dip_6_300mil.fzp", 270, 87, {"chip label": "74LVC2G17"}),
    "C1": ("100milCeramicCapacitorModuleID", None, 333, 36, {"capacitance": "100nF"}),
    "J2": ("generic_male_pin_header_4_100mil", f"{PF}/generic_male_pin_header_4_100mil.fzp", 396, 99, {}),
    "FX2": ("generic_female_pin_header_10_100mil", f"{PF}/generic_female_pin_header_10_100mil.fzp", 459, 171, {}),
    "PI": ("raspberry_pi_3_rev-1.2", f"{CORE}/Raspberry Pi 3.fzp", 594, 18, {}),
}

COLORS = {"SDA": "#418dd9", "SCL": "#f2c600", "0V": "#404040", "3V3": "#cc1414"}
WIRES = [
    # (net, (pièce, connecteur), (pièce, connecteur))
    ("SDA", ("BA", "connector0"), ("R1", "connector0")),
    ("SCL", ("BA", "connector1"), ("R2", "connector0")),
    ("0V", ("BA", "connector2"), ("D1", "connector2")),
    ("SDA", ("R1", "connector1"), ("R3", "connector0")),
    ("SDA", ("R3", "connector0"), ("D1", "connector0")),
    ("SDA", ("D1", "connector0"), ("U1", "connector2")),
    ("SCL", ("R2", "connector1"), ("R4", "connector0")),
    ("SCL", ("R4", "connector0"), ("D1", "connector1")),
    ("SCL", ("D1", "connector1"), ("U1", "connector0")),
    ("0V", ("R3", "connector1"), ("R4", "connector1")),
    ("0V", ("R4", "connector1"), ("D1", "connector2")),
    ("0V", ("D1", "connector2"), ("U1", "connector1")),
    ("0V", ("U1", "connector1"), ("C1", "connector1")),
    ("0V", ("C1", "connector1"), ("J2", "connector0")),
    ("3V3", ("U1", "connector4"), ("C1", "connector0")),
    ("3V3", ("C1", "connector0"), ("J2", "connector3")),
    ("SCL", ("U1", "connector5"), ("J2", "connector1")),
    ("SDA", ("U1", "connector3"), ("J2", "connector2")),
    ("0V", ("J2", "connector0"), ("FX2", "connector9")),
    ("SCL", ("J2", "connector1"), ("FX2", "connector0")),
    ("SDA", ("J2", "connector2"), ("FX2", "connector1")),
    ("3V3", ("J2", "connector3"), ("PI", "connector0")),
]

NOTES = [
    ("Sonde I2C passive — espion du bus BP / BA Essensys (lecture seule) — feature i2c-ba-sniffer-2026-10-009", 0, -45, 560, 32),
    ("BA J1/J2 (WR-MPC3 2x2) : 1 SDA, 2 SCL, 3 0 V. Position 4 = +15 V : VIDE, ne jamais raccorder. "
     "Branchement hors tension, par une personne habilitée.", -18, 225, 170, 80),
    ("Plaque à pastilles : R1/R2 1 kΩ série, R3/R4 1 MΩ, D1 SP0502BAHT (adaptateur SOT-23 vers SIP3), "
     "U1 74LVC2G17 (adaptateur SC-70 vers DIP6), C1 100 nF. Aucune pull-up.", 162, 225, 230, 80),
    ("Analyseur FX2 : CH0 = SCL, CH1 = SDA, GND. USB vers le Raspberry Pi.", 405, 225, 170, 60),
    ("Raspberry Pi SUR BATTERIE, Wi-Fi seulement : ni Ethernet ni chargeur secteur (pas de pont de masse). "
     "+3,3 V de la sonde : broche 1 du GPIO.", 594, 225, 300, 60),
]


def _instance(idx: int, title: str, module: str, fzp: str, x: float, y: float, props: dict) -> str:
    p = "".join(f'<property name="{html.escape(k)}" value="{html.escape(v)}"/>' for k, v in props.items())
    # Chemin neutre : Fritzing résout la pièce par moduleIdRef (aucun chemin local dans le dépôt public).
    path = f":/resources/parts/core/{os.path.basename(fzp) if fzp else module + '.fzp'}"
    return (f'<instance moduleIdRef="{module}" modelIndex="{idx}" path="{html.escape(path)}">{p}<title>{title}</title><views>'
            f'<breadboardView layer="breadboard"><geometry z="2.5" x="{x:.3f}" y="{y:.3f}"/></breadboardView>'
            f'</views></instance>')


def main() -> None:
    capacitor = next(os.path.join(CORE, f) for f in os.listdir(CORE)
                     if f.endswith(".fzp") and 'moduleId="100milCeramicCapacitorModuleID"' in open(os.path.join(CORE, f), encoding="utf-8").read())
    index, points, out = {}, {}, []
    for i, (title, (module, fzp, x, y, props)) in enumerate(PARTS.items()):
        fzp = fzp or capacitor
        index[title] = 1000 + i
        svg, conns = part_info(fzp)
        pts = connector_points(svg, list(conns.values()))
        points[title] = {c: (x + pts[sid][0], y + pts[sid][1]) for c, sid in conns.items()}
        out.append(_instance(index[title], title, module, fzp if title != "C1" else fzp, x, y, props))
    for k, (net, (pa, ca), (pb, cb)) in enumerate(WIRES):
        (x1, y1), (x2, y2) = points[pa][ca], points[pb][cb]
        idx = 2000 + k
        out.append(
            f'<instance moduleIdRef="WireModuleID" modelIndex="{idx}" path=":/resources/parts/core/wire.fzp"><title>Fil{k + 1} {net}</title><views>'
            f'<breadboardView layer="breadboardWire"><geometry z="3.5" x="{x1:.3f}" y="{y1:.3f}" x1="0" y1="0" x2="{x2 - x1:.3f}" y2="{y2 - y1:.3f}" wireFlags="64"/>'
            f'<wireExtras mils="22.2222" color="{COLORS[net]}" opacity="1" banded="0"/><connectors>'
            f'<connector connectorId="connector0" layer="breadboardWire"><geometry x="0" y="0"/><connects>'
            f'<connect connectorId="{ca}" modelIndex="{index[pa]}" layer="breadboardbreadboard"/></connects></connector>'
            f'<connector connectorId="connector1" layer="breadboardWire"><geometry x="0" y="0"/><connects>'
            f'<connect connectorId="{cb}" modelIndex="{index[pb]}" layer="breadboardbreadboard"/></connects></connector>'
            f'</connectors></breadboardView></views></instance>')
    for k, (txt, x, y, w, h) in enumerate(NOTES):
        out.append(f'<instance moduleIdRef="NoteModuleID" modelIndex="{3000 + k}" path=":/resources/parts/core/note.fzp"><title>Note{k + 1}</title>'
                   f'<text>{html.escape(txt)}</text><views><breadboardView layer="breadboardNote">'
                   f'<geometry z="5" x="{x}" y="{y}" width="{w}" height="{h}"/></breadboardView></views></instance>')
    fz = ('<?xml version="1.0" encoding="UTF-8"?>\n<module fritzingVersion="1.0.2"><views>'
          '<view name="breadboardView" backgroundColor="#ffffff" gridSize="0.1in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>'
          '<view name="schematicView" backgroundColor="#ffffff" gridSize="0.1in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>'
          '<view name="pcbView" backgroundColor="#333333" gridSize="0.05in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>'
          '</views><instances>\n' + "\n".join(out) + "\n</instances></module>\n")
    target = os.path.join(HERE, NAME + ".fzz")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(NAME + ".fz", date_time=(2026, 10, 13, 0, 0, 0))
        z.writestr(info, fz)
    print("ok", target, len(WIRES), "fils")


if __name__ == "__main__":
    main()
