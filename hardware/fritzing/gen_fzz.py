#!/usr/bin/env python3
"""Génère les deux croquis Fritzing de la sonde passive (vue platine).

Feature i2c-ba-sniffer-2026-10-009 (essensys-hub/essensys-feature-lifecycle#29), tâche 5.4,
corrections après relecture (essensys-hub/essensys-i2c-ba-sniffer#5).

- ``sonde-i2c-passive-implantation.fzz`` : plaque à pastilles vue de dessus, repères et valeurs
  lisibles, fils à angle droit, bus 0 V en anneau, deux croisements de fils isolés signalés.
- ``sonde-i2c-passive-ensemble.fzz`` : BA → câble 3 fils → sonde → analyseur FX2 → Raspberry Pi
  sur batterie (câble USB, masse commune, Ethernet barré, zone « même 0 V que l'armoire »).

Toutes les pièces sont dessinées ici (pièces Fritzing embarquées dans le .fzz), sauf le
Raspberry Pi 3 (pièce de base Fritzing). Unité : px de vue platine, 90 px par pouce
(pas de la plaque : 0,1 po = 9 px).

Usage : ``python3 hardware/fritzing/gen_fzz.py`` puis
``/Applications/Fritzing.app/Contents/MacOS/Fritzing -svg <dossier contenant les .fzz>``.
"""

from __future__ import annotations

import html
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
P = 9.0  # pas de 0,1 po
FONT = "DejaVu Sans, Arial, Helvetica, sans-serif"
COL = {"SCL": "#e0b000", "SDA": "#2f6fd0", "0V": "#202020", "3V3": "#d01c1c", "USB": "#7a7a7a"}
STAMP = (2026, 10, 13, 0, 0, 0)


def esc(t: str) -> str:
    return html.escape(t, quote=True)


def txt(x, y, s, size=4.5, anchor="start", color="#111", weight="normal"):
    return (f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-family="{FONT}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{esc(s)}</text>')


# ---------------------------------------------------------------- pièces
class Part:
    def __init__(self, mid, title, w, h, body, pins, label="X"):
        """``pins`` : liste ordonnée de (nom, x, y) en coordonnées locales."""
        self.mid, self.title, self.w, self.h, self.body, self.label = mid, title, w, h, body, label
        self.pins = list(pins)
        self.core = False

    def pin(self, name):
        for n, x, y in self.pins:
            if n == name:
                return x, y
        raise KeyError(name)

    def cid(self, name):
        if self.core:
            return name
        return "connector%d" % [n for n, _, _ in self.pins].index(name)

    def files(self):
        conns = ""
        for i, (n, _, _) in enumerate(self.pins):
            conns += (f'<connector id="connector{i}" name="{esc(n)}" type="male"><description>{esc(n)}</description><views>'
                      f'<breadboardView><p layer="breadboard" svgId="connector{i}pin"/></breadboardView>'
                      f'<schematicView><p layer="schematic" svgId="connector{i}pin"/></schematicView>'
                      f'<pcbView><p layer="copper0" svgId="connector{i}pin"/><p layer="copper1" svgId="connector{i}pin"/></pcbView>'
                      f'</views></connector>')
        fzp = (f'<?xml version="1.0" encoding="UTF-8"?>\n<module fritzingVersion="1.0.2" moduleId="{self.mid}"><version>1</version>'
               f'<title>{esc(self.title)}</title><label>{esc(self.label)}</label><author>Essensys</author>'
               f'<properties><property name="family">essensys-sonde</property></properties><description>{esc(self.title)}</description>'
               f'<views><iconView><layers image="breadboard/{self.mid}_bb.svg"><layer layerId="icon"/></layers></iconView>'
               f'<breadboardView><layers image="breadboard/{self.mid}_bb.svg"><layer layerId="breadboard"/></layers></breadboardView>'
               f'<schematicView><layers image="schematic/{self.mid}_sch.svg"><layer layerId="schematic"/></layers></schematicView>'
               f'<pcbView><layers image="pcb/{self.mid}_pcb.svg"><layer layerId="copper0"/><layer layerId="copper1"/></layers></pcbView>'
               f'</views><connectors>{conns}</connectors></module>\n')
        head = f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w / 90:.5f}in" height="{self.h / 90:.5f}in" viewBox="0 0 {self.w} {self.h}">'
        hidden = "".join(f'<rect id="connector{i}pin" x="{x - 1.5:.2f}" y="{y - 1.5:.2f}" width="3" height="3" fill="none" stroke="none"/>'
                         for i, (_, x, y) in enumerate(self.pins))
        return {
            f"part.{self.mid}.fzp": fzp,
            f"svg.breadboard.{self.mid}_bb.svg": f'{head}<g id="breadboard">{self.body}{hidden}</g></svg>',
            f"svg.schematic.{self.mid}_sch.svg": f'{head}<g id="schematic">{hidden}</g></svg>',
            f"svg.pcb.{self.mid}_pcb.svg": f'{head}<g id="copper0"><g id="copper1">{hidden}</g></g></svg>',
        }


def lead(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#9a9a9a" stroke-width="1.1" stroke-linecap="round"/>'


def pad(x, y):
    return f'<circle cx="{x}" cy="{y}" r="2.1" fill="#c8a24a" stroke="#8a6a20" stroke-width="0.5"/><circle cx="{x}" cy="{y}" r="0.8" fill="#3a2a10"/>'


BANDS = {"1k": ["#7a4a1a", "#111", "#d02020", "#c9a227"], "1M": ["#7a4a1a", "#111", "#2a9a2a", "#c9a227"]}


def resistor(mid, ref, value, vertical=False):
    bands = BANDS["1k" if value.startswith("1 k") else "1M"]
    if not vertical:  # broches à 0,4 po
        w, h, y = 45, 18, 13.5
        body = lead(4.5, y, 13.5, y) + lead(31.5, y, 40.5, y) + pad(4.5, y) + pad(40.5, y)
        body += f'<rect x="13.5" y="{y - 3.2}" width="18" height="6.4" rx="2.4" fill="#e3c58f" stroke="#a88a50" stroke-width="0.5"/>'
        body += "".join(f'<rect x="{16.2 + 3.4 * k}" y="{y - 3.2}" width="1.6" height="6.4" fill="{c}"/>' for k, c in enumerate(bands))
        body += txt(22.5, 6.5, f"{ref} · {value}", 4.6, "middle", weight="bold")
        return Part(mid, f"{ref} {value}", w, h, body, [("1", 4.5, y), ("2", 40.5, y)], ref)
    w, h, x = 46, 45, 4.5
    body = lead(x, 4.5, x, 13.5) + lead(x, 31.5, x, 40.5) + pad(x, 4.5) + pad(x, 40.5)
    body += f'<rect x="{x - 3.2}" y="13.5" width="6.4" height="18" rx="2.4" fill="#e3c58f" stroke="#a88a50" stroke-width="0.5"/>'
    body += "".join(f'<rect x="{x - 3.2}" y="{16.2 + 3.4 * k}" width="6.4" height="1.6" fill="{c}"/>' for k, c in enumerate(bands))
    body += txt(10.5, 21, ref, 4.6, weight="bold") + txt(10.5, 27, value, 4.3)
    return Part(mid, f"{ref} {value}", w, h, body, [("1", x, 4.5), ("2", x, 40.5)], ref)


def build_parts():
    parts = {}
    parts["R1"] = resistor("essensys_sonde_r1", "R1", "1 kΩ")
    parts["R2"] = resistor("essensys_sonde_r2", "R2", "1 kΩ")
    parts["R3"] = resistor("essensys_sonde_r3", "R3", "1 MΩ", vertical=True)
    parts["R4"] = resistor("essensys_sonde_r4", "R4", "1 MΩ", vertical=True)

    # D1 : adaptateur SOT-23 vers SIP3, debout (vue de dessus : la tranche de la carte) ; libellés à gauche
    b = '<rect x="36" y="11.6" width="27" height="3.8" rx="0.8" fill="#1d6a3c" stroke="#0f3f22" stroke-width="0.5"/>'
    b += pad(40.5, 13.5) + pad(49.5, 13.5) + pad(58.5, 13.5)
    b += txt(34, 8, "D1 SP0502BAHT", 4.2, "end", weight="bold") + txt(34, 13.8, "adaptateur SOT-23", 3.4, "end", "#444")
    b += txt(34, 19.5, "1 SDA · 2 SCL · 3 0 V", 3.4, "end", "#444")
    parts["D1"] = Part("essensys_sonde_d1", "D1 SP0502BAHT sur adaptateur SIP3", 64, 22, b,
                       [("1", 40.5, 13.5), ("2", 49.5, 13.5), ("3", 58.5, 13.5)], "D1")

    # U1 : adaptateur SC-70 vers DIP6 (broches gauche 1-2-3, droite 6-5-4 ; colonnes à 0,3 po)
    b = '<rect x="0.5" y="0.5" width="44" height="35" rx="2" fill="#1d6a3c" stroke="#0f3f22" stroke-width="0.6"/>'
    for yy in (9, 18, 27):
        b += pad(9, yy) + pad(36, yy)
    b += '<rect x="19" y="13" width="7" height="10" rx="0.8" fill="#151515"/>'
    b += txt(22.5, 8.5, "U1", 4.6, "middle", "#fff", "bold") + txt(22.5, 33, "74LVC2G17", 3.6, "middle", "#fff")
    for n, yy in (("1", 9), ("2", 18), ("3", 27)):
        b += txt(13, yy + 1.3, n, 3.3, color="#fff")
    for n, yy in (("6", 9), ("5", 18), ("4", 27)):
        b += txt(32, yy + 1.3, n, 3.3, "end", "#fff")
    parts["U1"] = Part("essensys_sonde_u1", "U1 74LVC2G17 sur adaptateur DIP6", 45, 36, b,
                       [("1", 9, 9), ("2", 9, 18), ("3", 9, 27), ("4", 36, 27), ("5", 36, 18), ("6", 36, 9)], "U1")

    # C1 : condensateur céramique, broches à 0,3 po
    b = lead(4.5, 4.5, 4.5, 31.5) + pad(4.5, 4.5) + pad(4.5, 31.5)
    b += '<ellipse cx="4.5" cy="18" rx="3.6" ry="5.2" fill="#3a78c8" stroke="#1f4f8a" stroke-width="0.5"/>'
    b += txt(10.5, 16.5, "C1", 4.6, weight="bold") + txt(10.5, 22.5, "100 nF", 4.3)
    parts["C1"] = Part("essensys_sonde_c1", "C1 100 nF", 36, 36, b, [("1", 4.5, 4.5), ("2", 4.5, 31.5)], "C1")

    # J2 : barrette mâle 1x4 vers l'analyseur
    b = '<rect x="1.2" y="19.2" width="6.6" height="34.6" rx="1" fill="#1a1a1a"/>'
    for k in range(4):
        b += f'<rect x="3.3" y="{20.3 + 9 * k + 2.2}" width="2.4" height="2.4" fill="#d9b44a"/>'
    b += txt(0, 5, "J2 vers l'analyseur (de haut en bas)", 4.3, weight="bold")
    b += txt(0, 11, "1 +3,3 V · 2 SCL (D0) · 3 SDA (D1) · 4 0 V", 3.8)
    parts["J2"] = Part("essensys_sonde_j2", "J2 barrette 1x4 vers analyseur", 76, 55, b,
                       [("1", 4.5, 22.5), ("2", 4.5, 31.5), ("3", 4.5, 40.5), ("4", 4.5, 49.5)], "J2")

    # J1 : boîtier WR-MPC3 2x2 serti, côté câble (face d'accouplement vue de face)
    b = '<rect x="2" y="10" width="34" height="34" rx="3" fill="#f2f2ee" stroke="#555" stroke-width="0.8"/>'
    cav = {"1": (11, 19), "2": (27, 19), "3": (11, 35), "4": (27, 35)}
    for n, (cx, cy) in cav.items():
        b += f'<rect x="{cx - 5}" y="{cy - 5}" width="10" height="10" rx="1.2" fill="#d8d8d0" stroke="#666" stroke-width="0.6"/>'
        b += txt(cx, cy + 1.6, n, 4.6, "middle", weight="bold")
    b += '<line x1="22" y1="30" x2="32" y2="40" stroke="#d01c1c" stroke-width="1.6"/><line x1="32" y1="30" x2="22" y2="40" stroke="#d01c1c" stroke-width="1.6"/>'
    b += txt(0, 52, "J1 : câble vers le BA", 4.2, weight="bold") + txt(0, 58, "(WR-MPC3 2x2, vue de face)", 3.6)
    b += txt(0, 64, "1 SDA · 2 SCL · 3 0 V", 3.8)
    b += txt(0, 70, "4 = +15 V : contact VIDE", 3.8, color="#d01c1c", weight="bold")
    b += '<rect x="36" y="22" width="14" height="12" fill="#3b3b3b"/>'
    parts["J1"] = Part("essensys_sonde_j1", "J1 boîtier WR-MPC3 2x2, position 4 vide", 64, 74, b,
                       [("0V", 50, 24), ("SCL", 50, 28), ("SDA", 50, 32)], "J1")
    return parts


def board(cols, rows, junctions=()):
    w, h = cols * P, rows * P
    b = f'<rect x="0" y="0" width="{w}" height="{h}" rx="3" fill="#d7c08a" stroke="#9c8650" stroke-width="0.8"/>'
    for i in range(cols):
        for j in range(rows):
            cx, cy = 4.5 + P * i, 4.5 + P * j
            b += f'<circle cx="{cx}" cy="{cy}" r="2.2" fill="#c49a3a"/><circle cx="{cx}" cy="{cy}" r="0.9" fill="#4a3a20"/>'
    for i, j in junctions:  # points de soudure des jonctions (sous les fils, plus larges qu'eux)
        b += f'<circle cx="{4.5 + P * i}" cy="{4.5 + P * j}" r="3.4" fill="#111"/>'
    return Part("essensys_sonde_plaque", "Plaque à pastilles (vue de dessus)", w, h, b, [], "PL")


def box(mid, title, w, h, body, pins=(), label="X"):
    return Part(mid, title, w, h, body, list(pins), label)


def legend(mid, lines, w, h, title, k=1.0):
    b = f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="3" fill="#ffffff" stroke="#999" stroke-width="0.6"/>'
    b += txt(5, 9 * k, title, 4.6 * k, weight="bold")
    y = 17 * k
    for kind, color, text in lines:
        if kind == "wire":
            b += f'<line x1="5" y1="{y - 1.5}" x2="20" y2="{y - 1.5}" stroke="{color}" stroke-width="2.4" stroke-linecap="round"/>'
            b += txt(24, y, text, 4 * k)
        elif kind == "cross":
            b += (f'<line x1="5" y1="{y - 1.5}" x2="20" y2="{y - 1.5}" stroke="#2f6fd0" stroke-width="2.4"/>'
                  f'<line x1="12.5" y1="{y - 7}" x2="12.5" y2="{y + 4}" stroke="#202020" stroke-width="2.4"/>')
            b += txt(24, y, text, 4 * k)
        else:
            b += txt(5, y, text, 3.8 * k, color=color)
        y += 8 * k
    return Part(mid, title, w, h, b, [], "LG")


def title_part(mid, text, sub, w):
    b = txt(0, 8, text, 7, weight="bold") + txt(0, 16, sub, 4.4, color="#444")
    return Part(mid, text, w, 19, b, [], "TT")


# ---------------------------------------------------------------- croquis
class Sketch:
    def __init__(self, name):
        self.name, self.instances, self.parts, self.idx, self.pos = name, [], {}, {}, {}
        self.wires = []  # (net, extrémité a, coudes, extrémité b)
        self.n = 1000

    def add(self, key, part, x, y, z=2.5):
        self.n += 1
        self.idx[key], self.parts[key], self.pos[key] = self.n, part, (x, y)
        self.instances.append(f'<instance moduleIdRef="{part.mid}" modelIndex="{self.n}" path="{part.mid}.fzp"><title>{esc(key)}</title>'
                              f'<views><breadboardView layer="breadboard"><geometry z="{z}" x="{x:.3f}" y="{y:.3f}"/></breadboardView></views></instance>')

    def add_core(self, key, module, fzp_name, x, y, pins, z=2.4):
        """Pièce de base Fritzing ; ``pins`` : (identifiant de connecteur, x, y) relevés dans son SVG."""
        self.n += 1
        part = Part(module, key, 0, 0, "", pins)
        part.core = True
        self.idx[key], self.parts[key], self.pos[key] = self.n, part, (x, y)
        self.instances.append(f'<instance moduleIdRef="{module}" modelIndex="{self.n}" path=":/resources/parts/core/{esc(fzp_name)}"><title>{esc(key)}</title>'
                              f'<views><breadboardView layer="breadboard"><geometry z="{z}" x="{x:.3f}" y="{y:.3f}"/></breadboardView></views></instance>')

    def at(self, key, pin):
        x, y = self.pos[key]
        px, py = self.parts[key].pin(pin)
        return (round(x + px, 3), round(y + py, 3))

    def put(self, key, part, pin, hole_xy, z=2.5):
        """Place ``part`` de sorte que sa broche ``pin`` tombe sur le trou ``hole_xy``."""
        px, py = part.pin(pin)
        self.add(key, part, hole_xy[0] - px, hole_xy[1] - py, z)

    def route(self, net, a, pts, b):
        """a, b : ("P", clé, broche) ou ("N", nom, (x, y)) ; pts : coudes intermédiaires."""
        self.wires.append((net, a, list(pts), b))

    def point(self, end):
        return self.at(end[1], end[2]) if end[0] == "P" else end[2]

    def build(self):
        segs = []  # (net, p1, p2, clé1, clé2)
        for w, (net, a, pts, b) in enumerate(self.wires):
            path = [self.point(a)] + pts + [self.point(b)]
            keys = [("P", a[1], a[2]) if a[0] == "P" else ("N", a[1])]
            keys += [("B", w, k) for k in range(len(pts))]
            keys += [("P", b[1], b[2]) if b[0] == "P" else ("N", b[1])]
            for k in range(len(path) - 1):
                segs.append((net, path[k], path[k + 1], keys[k], keys[k + 1]))
        ends = {}
        for s, seg in enumerate(segs):
            for side in (0, 1):
                ends.setdefault(seg[3 + side], []).append((s, side))
        out = []
        for s, (net, p1, p2, ka, kb) in enumerate(segs):
            conns = []
            for side, key in ((0, ka), (1, kb)):
                c = []
                if key[0] == "P":
                    part = self.parts[key[1]]
                    c.append(f'<connect connectorId="{part.cid(key[2])}" modelIndex="{self.idx[key[1]]}" layer="breadboard"/>')
                for (o, oside) in ends[key]:
                    if (o, oside) != (s, side):
                        c.append(f'<connect connectorId="connector{oside}" modelIndex="{5000 + o}" layer="breadboardWire"/>')
                conns.append(f'<connector connectorId="connector{side}" layer="breadboardWire"><geometry x="0" y="0"/><connects>{"".join(c)}</connects></connector>')
            width = "30" if net == "USB" else "13"
            out.append(f'<instance moduleIdRef="WireModuleID" modelIndex="{5000 + s}" path=":/resources/parts/core/wire.fzp"><title>Fil {net} {s}</title><views>'
                       f'<breadboardView layer="breadboardWire"><geometry z="3.5" x="{p1[0]:.3f}" y="{p1[1]:.3f}" x1="0" y1="0" '
                       f'x2="{p2[0] - p1[0]:.3f}" y2="{p2[1] - p1[1]:.3f}" wireFlags="64"/>'
                       f'<wireExtras mils="{width}" color="{COL[net]}" opacity="1" banded="0"/><connectors>{"".join(conns)}</connectors>'
                       f'</breadboardView></views></instance>')
        fz = ('<?xml version="1.0" encoding="UTF-8"?>\n<module fritzingVersion="1.0.2"><views>'
              '<view name="breadboardView" backgroundColor="#ffffff" gridSize="0.1in" showGrid="0" alignToGrid="1" viewFromBelow="0"/>'
              '<view name="schematicView" backgroundColor="#ffffff" gridSize="0.1in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>'
              '<view name="pcbView" backgroundColor="#333333" gridSize="0.05in" showGrid="1" alignToGrid="1" viewFromBelow="0"/>'
              '</views><instances>\n' + "\n".join(self.instances + out) + "\n</instances></module>\n")
        target = os.path.join(HERE, self.name + ".fzz")
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(zipfile.ZipInfo(self.name + ".fz", date_time=STAMP), fz)
            seen = set()
            for part in self.parts.values():
                if part.core or part.mid in seen:
                    continue
                seen.add(part.mid)
                for k, v in sorted(part.files().items()):
                    z.writestr(zipfile.ZipInfo(k, date_time=STAMP), v)
        return target, len(segs)


def H(i, j):
    """Centre du trou (colonne i, rangée j) de la plaque posée en (0, 0)."""
    return (4.5 + P * i, 4.5 + P * j)


# ------------------------------------------------------------ implantation
def implantation():
    sk = Sketch("sonde-i2c-passive-implantation")
    pt = build_parts()
    cols, rows = 34, 15
    sk.add("plaque", board(cols, rows, [(13, 4), (12, 10), (15, 7), (15, 14), (25, 14)]), 0, 0, z=1.0)
    sk.add("titre", title_part("essensys_sonde_titre_impl", "Sonde I2C passive — implantation sur plaque à pastilles",
                               "Vue de dessus · pas 2,54 mm · feature i2c-ba-sniffer-2026-10-009", 330), -80, -44, z=4)
    sk.put("R2", pt["R2"], "1", H(3, 4))
    sk.put("R1", pt["R1"], "1", H(3, 10))
    sk.put("R4", pt["R4"], "1", H(9, 0))
    sk.put("R3", pt["R3"], "1", H(9, 10))
    sk.put("D1", pt["D1"], "1", H(12, 7))
    sk.put("U1", pt["U1"], "1", H(17, 6))
    sk.put("C1", pt["C1"], "1", H(27, 5))
    sk.put("J2", pt["J2"], "1", H(25, 5))
    sk.add("J1", pt["J1"], -84, H(0, 5)[1] - 28)

    def N(name, i, j):
        return ("N", name, H(i, j))

    def Pp(key, pin):
        return ("P", key, pin)

    # câble J1 → plaque
    x0 = sk.at("J1", "0V")[0]
    sk.route("0V", Pp("J1", "0V"), [(x0 + 6, sk.at("J1", "0V")[1]), (x0 + 6, H(0, 0)[1])], N("tl", 0, 0))
    sk.route("SCL", Pp("J1", "SCL"), [(x0 + 12, sk.at("J1", "SCL")[1]), (x0 + 12, H(0, 4)[1])], Pp("R2", "1"))
    sk.route("SDA", Pp("J1", "SDA"), [(x0 + 18, sk.at("J1", "SDA")[1]), (x0 + 18, H(0, 10)[1])], Pp("R1", "1"))
    # bus 0 V en anneau (haut, côté droit, bas)
    sk.route("0V", N("tl", 0, 0), [], Pp("R4", "1"))
    sk.route("0V", Pp("R4", "1"), [], N("tr", 33, 0))
    sk.route("0V", N("tr", 33, 0), [], N("br", 33, 14))
    sk.route("0V", N("br", 33, 14), [], N("b25", 25, 14))
    sk.route("0V", N("b25", 25, 14), [], N("b15", 15, 14))
    sk.route("0V", N("b15", 15, 14), [], Pp("R3", "2"))
    # SCL
    sk.route("SCL", Pp("R2", "2"), [], Pp("R4", "2"))
    sk.route("SCL", Pp("R4", "2"), [], N("s13", 13, 4))
    sk.route("SCL", N("s13", 13, 4), [], Pp("D1", "2"))
    sk.route("SCL", N("s13", 13, 4), [H(17, 4)], Pp("U1", "1"))
    # SDA
    sk.route("SDA", Pp("R1", "2"), [], Pp("R3", "1"))
    sk.route("SDA", Pp("R3", "1"), [], N("d12", 12, 10))
    sk.route("SDA", N("d12", 12, 10), [], Pp("D1", "1"))
    sk.route("SDA", N("d12", 12, 10), [H(17, 10)], Pp("U1", "3"))
    # 0 V de D1 et U1 : cavalier isolé jusqu'au bus (croise SDA)
    sk.route("0V", Pp("D1", "3"), [], N("g15", 15, 7))
    sk.route("0V", N("g15", 15, 7), [], Pp("U1", "2"))
    sk.route("0V", N("g15", 15, 7), [], N("b15", 15, 14))
    # sorties et alimentation (le +3,3 V croise SCL en cavalier isolé)
    sk.route("SCL", Pp("U1", "6"), [], Pp("J2", "2"))
    sk.route("SDA", Pp("U1", "4"), [H(23, 8), H(23, 7)], Pp("J2", "3"))
    sk.route("3V3", Pp("U1", "5"), [H(22, 7), H(22, 5)], Pp("J2", "1"))
    sk.route("3V3", Pp("J2", "1"), [], Pp("C1", "1"))
    sk.route("0V", Pp("J2", "4"), [], Pp("C1", "2"))
    sk.route("0V", Pp("J2", "4"), [], N("b25", 25, 14))
    lg = legend("essensys_sonde_legende_impl", [
        ("wire", COL["SCL"], "SCL"), ("wire", COL["SDA"], "SDA"), ("wire", COL["0V"], "0 V (bus en anneau)"),
        ("wire", COL["3V3"], "+3,3 V"), ("cross", "", "croisement : fils isolés, sans contact"),
        ("text", "#444", "Point noir : jonction soudée. Fils sous la plaque ou en cavaliers isolés."),
        ("text", "#d01c1c", "Aucune pull-up · jamais le +15 V (position 4 de J1 vide)."),
    ], 196, 72, "Légende")
    sk.add("legende", lg, 0, H(0, 15)[1] + 4, z=4)
    return sk


# ------------------------------------------------------------ ensemble
def ensemble():
    sk = Sketch("sonde-i2c-passive-ensemble")
    sk.add("titre", title_part("essensys_sonde_titre_ens", "Sonde I2C passive — montage d'ensemble",
                               "BA, câble 3 fils, sonde, analyseur FX2, Raspberry Pi sur batterie", 400), 0, -6, z=4)
    # zones
    z1 = ('<rect x="1" y="1" width="168" height="208" rx="6" fill="#ffb000" fill-opacity="0.08" stroke="#d08a00" stroke-width="1.2" stroke-dasharray="5 3"/>'
          + txt(8, 12, "Armoire (TBTS)", 6.2, color="#a06000", weight="bold") + txt(8, 19, "0 V jamais relié au PE", 5.0, color="#a06000"))
    sk.add("zone_armoire", box("essensys_sonde_zone_armoire", "Zone armoire", 170, 210, z1), 0, 20, z=1.0)
    z2 = ('<rect x="1" y="1" width="718" height="338" rx="6" fill="#2f6fd0" fill-opacity="0.06" stroke="#2f6fd0" stroke-width="1.2" stroke-dasharray="5 3"/>'
          + txt(8, 12, "Hôte de capture : il partage le 0 V de l'armoire dès que la sonde est branchée", 6.2, color="#1f4f9a", weight="bold")
          + txt(8, 20, "Tout ce cadre reste isolé du PE : batterie, Wi-Fi seulement, ni câble Ethernet ni chargeur secteur.", 5.0, color="#1f4f9a"))
    sk.add("zone_hote", box("essensys_sonde_zone_hote", "Zone hôte", 720, 340, z2), 190, 20, z=1.0)
    # BA en bout de chaîne, connecteur libre et câble enfiché
    b = ('<rect x="0" y="0" width="140" height="96" rx="4" fill="#1d6a3c" stroke="#0f3f22" stroke-width="0.8"/>'
         + txt(8, 14, "BA en bout de chaîne", 7, "start", "#fff", "bold") + txt(8, 23, "(ex. SC940D, pièces de vie)", 5.2, "start", "#fff")
         + txt(8, 86, "J1/J2 : 1 SDA · 2 SCL · 3 0 V · 4 +15 V", 5.0, "start", "#ffe9a8"))
    b += '<rect x="96" y="34" width="38" height="38" rx="3" fill="#f2f2ee" stroke="#555" stroke-width="0.8"/>'
    for n, (cx, cy) in {"1": (106, 44), "2": (124, 44), "3": (106, 62), "4": (124, 62)}.items():
        b += (f'<rect x="{cx - 5}" y="{cy - 5}" width="10" height="10" rx="1.2" fill="#d8d8d0" stroke="#666" stroke-width="0.6"/>'
              + txt(cx, cy + 1.6, n, 4.6, "middle", weight="bold"))
    b += '<line x1="119" y1="57" x2="129" y2="67" stroke="#d01c1c" stroke-width="1.6"/><line x1="129" y1="57" x2="119" y2="67" stroke="#d01c1c" stroke-width="1.6"/>'
    b += '<rect x="134" y="44" width="8" height="18" fill="#3b3b3b"/>'
    sk.add("BA", box("essensys_sonde_ba", "BA, connecteur J1/J2 libre", 146, 96, b,
                     [("SDA", 142, 47), ("SCL", 142, 53), ("0V", 142, 59)]), 12, 60)
    t = (txt(0, 6, "Câble : boîtier WR-MPC3 2x2 enfiché,", 5.0, color="#333")
         + txt(0, 12, "contacts 1-2-3 sertis, 4 vide (+15 V).", 5.0, color="#d01c1c")
         + txt(0, 18, "Brancher et débrancher hors tension.", 5.0, color="#333"))
    sk.add("note_cable", box("essensys_sonde_note_cable", "Note câble", 160, 22, t), 10, 166, z=4)
    # sonde (carte simplifiée)
    b = ('<rect x="0" y="0" width="110" height="86" rx="4" fill="#d7c08a" stroke="#9c8650" stroke-width="0.8"/>'
         + txt(55, 14, "Sonde passive", 7, "middle", weight="bold") + txt(55, 22, "voir le plan d'implantation", 5.0, "middle", "#444")
         + txt(55, 34, "R1/R2 1 kΩ · R3/R4 1 MΩ", 5.0, "middle") + txt(55, 41, "D1 SP0502BAHT", 5.0, "middle")
         + txt(55, 48, "U1 74LVC2G17 · C1 100 nF", 5.0, "middle"))
    b += txt(4, 60, "J1", 5.0, weight="bold") + txt(106, 59, "J2", 5.0, "end", weight="bold")
    b += txt(4, 71.6, "SDA", 4.4) + txt(4, 77.6, "SCL", 4.4) + txt(4, 83.6, "0 V", 4.4)
    b += '<rect x="102" y="62" width="7" height="22" rx="1" fill="#1a1a1a"/>'
    for k, lab in enumerate(["1 +3,3 V", "2 SCL", "3 SDA", "4 0 V"]):
        b += txt(99, 66.6 + 5 * k, lab, 4.2, "end")
    sk.add("SONDE", box("essensys_sonde_carte", "Sonde passive", 110, 86, b,
                        [("in_SDA", 0, 70), ("in_SCL", 0, 76), ("in_0V", 0, 82),
                         ("1", 105.5, 65), ("2", 105.5, 70), ("3", 105.5, 75), ("4", 105.5, 80)]), 222, 64)
    # analyseur FX2
    labels = ["CH0", "CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CLK", "GND"]
    b = ('<rect x="10" y="0" width="100" height="96" rx="5" fill="#b8bec6" stroke="#6a7078" stroke-width="0.8"/>'
         + txt(60, 13, "Analyseur logique", 6.2, "middle", weight="bold") + txt(60, 20, "FX2 · 24 MHz · 8 voies", 5.0, "middle")
         + txt(62, 79, "1re voie = D0 (marquée CH0", 4.6, "middle", "#333") + txt(62, 86, "ou CH1 selon le modèle)", 4.6, "middle", "#333"))
    b += '<rect x="2" y="24" width="8" height="52" rx="1" fill="#1a1a1a"/>'
    for k, lab in enumerate(labels):
        y = 27 + 5 * k
        b += f'<rect x="4.6" y="{y - 1.3}" width="2.6" height="2.6" fill="#d9b44a"/>' + txt(13, y + 1.5, lab, 4.2)
    b += '<rect x="110" y="40" width="8" height="12" rx="1" fill="#8a8a8a"/>' + txt(106, 49, "USB", 4.6, "end")
    pins = [(lab, 6, 27 + 5 * k) for k, lab in enumerate(labels)] + [("USB", 118, 46)]
    sk.add("FX2", box("essensys_sonde_fx2", "Analyseur logique FX2", 120, 96, b, pins), 404, 58)
    # Raspberry Pi 3 (pièce de base) : broche 1 = connector0 (3,3 V), broche 9 = connector4 (GND)
    pi_x, pi_y = 578, 96
    sk.add_core("PI", "raspberry_pi_3_rev-1.2", "Raspberry Pi 3.fzp", pi_x, pi_y,
                [("connector0", 29.64, 15.44), ("connector4", 65.64, 15.44)])
    fiche = box("essensys_sonde_fiche_usb", "Fiche USB-A", 14, 12, '<rect x="1" y="2" width="12" height="8" rx="1" fill="#555"/>', [("in", 13, 6)])
    sk.add("USB_A", fiche, pi_x + 296, pi_y + 98 - 6, z=5)
    bat = ('<rect x="0" y="0" width="96" height="40" rx="6" fill="#2b2b2b" stroke="#111" stroke-width="0.8"/>'
           + txt(48, 16, "Batterie USB", 6.2, "middle", "#fff", "bold") + txt(48, 26, "(power bank)", 5.0, "middle", "#ddd")
           + '<rect x="96" y="15" width="5" height="10" fill="#555"/>')
    sk.add("BAT", box("essensys_sonde_batterie", "Batterie USB", 102, 40, bat, [("out", 101, 20)]), 430, 296)
    micro = box("essensys_sonde_fiche_micro", "Fiche micro-USB", 12, 12, '<rect x="2" y="1" width="8" height="10" rx="1" fill="#555"/>', [("in", 6, 11)])
    sk.add("MICRO", micro, pi_x + 37.5 - 6, pi_y + 205 - 6, z=5)
    interdit = ('<circle cx="22" cy="22" r="18" fill="none" stroke="#d01c1c" stroke-width="3"/>'
                '<line x1="9" y1="35" x2="35" y2="9" stroke="#d01c1c" stroke-width="3"/>' + txt(22, 50, "pas d'Ethernet", 4.6, "middle", "#d01c1c", "bold"))
    sk.add("NO_ETH", box("essensys_sonde_interdit_eth", "Pas d'Ethernet", 60, 54, interdit), pi_x + 262, pi_y + 145, z=5)

    def Pp(key, pin):
        return ("P", key, pin)

    xa = sk.at("BA", "SDA")[0] + 22
    sk.route("SDA", Pp("BA", "SDA"), [(xa, sk.at("BA", "SDA")[1]), (xa, sk.at("SONDE", "in_SDA")[1])], Pp("SONDE", "in_SDA"))
    sk.route("SCL", Pp("BA", "SCL"), [(xa + 8, sk.at("BA", "SCL")[1]), (xa + 8, sk.at("SONDE", "in_SCL")[1])], Pp("SONDE", "in_SCL"))
    sk.route("0V", Pp("BA", "0V"), [(xa + 16, sk.at("BA", "0V")[1]), (xa + 16, sk.at("SONDE", "in_0V")[1])], Pp("SONDE", "in_0V"))
    xs = sk.at("SONDE", "1")[0]
    sk.route("SCL", Pp("SONDE", "2"), [(xs + 22, sk.at("SONDE", "2")[1]), (xs + 22, sk.at("FX2", "CH0")[1])], Pp("FX2", "CH0"))
    sk.route("SDA", Pp("SONDE", "3"), [(xs + 30, sk.at("SONDE", "3")[1]), (xs + 30, sk.at("FX2", "CH1")[1])], Pp("FX2", "CH1"))
    sk.route("0V", Pp("SONDE", "4"), [(xs + 38, sk.at("SONDE", "4")[1]), (xs + 38, sk.at("FX2", "GND")[1])], Pp("FX2", "GND"))
    sk.route("0V", Pp("SONDE", "4"), [(xs + 38, sk.at("SONDE", "4")[1]), (xs + 38, 192), (sk.at("PI", "connector4")[0], 192)], Pp("PI", "connector4"))
    sk.route("3V3", Pp("SONDE", "1"), [(xs + 12, sk.at("SONDE", "1")[1]), (xs + 12, 44), (sk.at("PI", "connector0")[0], 44)], Pp("PI", "connector0"))
    ux, uy = sk.at("FX2", "USB")
    ax, ay = sk.at("USB_A", "in")
    sk.route("USB", Pp("FX2", "USB"), [(ux + 14, uy), (ux + 14, 350), (ax + 20, 350), (ax + 20, ay)], Pp("USB_A", "in"))
    bx, by = sk.at("BAT", "out")
    mx, my = sk.at("MICRO", "in")
    sk.route("USB", Pp("BAT", "out"), [(mx, by)], Pp("MICRO", "in"))
    lg = legend("essensys_sonde_legende_ens", [
        ("wire", COL["SCL"], "SCL (vers D0)"), ("wire", COL["SDA"], "SDA (vers D1)"), ("wire", COL["0V"], "0 V commun (analyseur et Pi)"),
        ("wire", COL["3V3"], "+3,3 V : broche 1 du GPIO"), ("wire", COL["USB"], "câble USB (relie aussi les 0 V)"),
        ("text", "#444", "GND du Pi : broche 9 du GPIO."),
    ], 186, 86, "Légende", k=1.3)
    sk.add("legende", lg, 0, 240, z=4)
    return sk


def main():
    for sk in (implantation(), ensemble()):
        target, n = sk.build()
        print("ok", os.path.basename(target), n, "segments")


if __name__ == "__main__":
    main()
