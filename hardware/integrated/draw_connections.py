#!/usr/bin/env python3
"""Illustrate the existing R0 contract; never generate PCB tracks or fabrication data.

Run with: uv run --with reportlab python hardware/integrated/draw_connections.py
Poppler (pdftoppm) is needed for the two PNG previews. SVG and PDF stay vector.
Component shapes, board outline and positions are explanatory proposals only.
"""
from html import escape
from pathlib import Path
import subprocess

from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.colors import toColor

HERE = Path(__file__).resolve().parent
OUT = HERE / "visuals"
W, H = 1600, 1100
INK, MUTED = "#163342", "#516C79"
BG, LINE = "#F3F7FA", "#D4E0E7"
USB, BUS, BP, BA = "#2673D5", "#007E81", "#7252B4", "#BF6B13"
OUT.mkdir(exist_ok=True)


class Page:
    def __init__(self, pdf, name):
        self.pdf, self.name = pdf, name
        self.svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
        self.svg += ['<style>text {font-family:Arial,Helvetica,sans-serif}</style>']
        self.rect(0, 0, W, H, BG, BG, 0)

    def rect(self, x, y, w, h, fill="white", stroke=LINE, radius=16, lw=2, dash=False):
        self.pdf.setFillColor(toColor(fill))
        self.pdf.setStrokeColor(toColor(stroke))
        self.pdf.setLineWidth(lw)
        self.pdf.setDash([8, 6] if dash else [])
        self.pdf.roundRect(x, H-y-h, w, h, radius, fill=1, stroke=1)
        d = ' stroke-dasharray="8 6"' if dash else ''
        self.svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{lw}"{d}/>')

    def text(self, x, y, text, size=22, color=INK, bold=False, anchor="start"):
        font = "Helvetica-Bold" if bold else "Helvetica"
        self.pdf.setFillColor(toColor(color))
        self.pdf.setFont(font, size)
        method = {"start": self.pdf.drawString, "middle": self.pdf.drawCentredString, "end": self.pdf.drawRightString}[anchor]
        method(x, H-y, text)
        self.svg.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}" text-anchor="{anchor}">{escape(text)}</text>')

    def paragraph(self, x, y, text, width, size=20, color=MUTED, leading=28, bold=False):
        font = "Helvetica-Bold" if bold else "Helvetica"
        for para in text.split("\n"):
            line = ""
            for word in para.split():
                test = f"{line} {word}".strip()
                if stringWidth(test, font, size) > width and line:
                    self.text(x, y, line, size, color, bold)
                    y += leading
                    line = word
                else:
                    line = test
            self.text(x, y, line, size, color, bold)
            y += leading
        return y

    def path(self, points, color=INK, width=3, dash=False):
        self.pdf.setStrokeColor(toColor(color))
        self.pdf.setLineWidth(width)
        self.pdf.setDash([10, 7] if dash else [])
        p = self.pdf.beginPath()
        p.moveTo(points[0][0], H-points[0][1])
        for x, y in points[1:]:
            p.lineTo(x, H-y)
        self.pdf.drawPath(p)
        coords = " ".join(f"{x},{y}" for x, y in points)
        d = ' stroke-dasharray="10 7"' if dash else ''
        self.svg.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"{d}/>')

    def circle(self, x, y, r, fill, stroke=None):
        stroke = stroke or fill
        self.pdf.setFillColor(toColor(fill))
        self.pdf.setStrokeColor(toColor(stroke))
        self.pdf.setLineWidth(2)
        self.pdf.setDash([])
        self.pdf.circle(x, H-y, r, fill=1, stroke=1)
        self.svg.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')

    def badge(self, x, y, width, label, color=USB, fill="#E9F2FF"):
        self.rect(x, y, width, 32, fill, fill, 16)
        self.text(x+width/2, y+22, label, 16, color, True, "middle")

    def chip(self, x, y, w, h, title, subtitle="", color="#263C45", pins=6):
        for i in range(pins):
            px = x + 12 + i * (w-24) / max(1, pins-1)
            self.rect(px-3, y-9, 6, 12, "#DCC78B", "#DCC78B", 0, 1)
            self.rect(px-3, y+h-3, 6, 12, "#DCC78B", "#DCC78B", 0, 1)
        self.rect(x, y, w, h, color, "#142A33", 7)
        self.circle(x+10, y+10, 3, "#E3E7E9")
        self.text(x+w/2, y+h/2+(0 if subtitle else 7), title, 21, "#FFFFFF", True, "middle")
        if subtitle:
            self.text(x+w/2, y+h/2+29, subtitle, 15, "#DEE8EC", False, "middle")

    def connector(self, x, y, w, h, count, color, rows=1):
        self.rect(x, y, w, h, "#FDFDFD", color, 5, 3)
        cols = count // rows
        for row in range(rows):
            for col in range(cols):
                px = x + (col+0.5) * w/cols
                py = y + (row+0.5) * h/rows
                self.rect(px-3, py-3, 6, 6, "#BBA464", "#8C783F", 0, 1)

    def header(self, number, title, subtitle):
        self.text(60, 45, "ESSENSYS / CARTE ANALYSEUR + PROGRAMMATEUR", 16, MUTED, True)
        self.text(60, 95, title, 38, INK, True)
        self.text(60, 132, subtitle, 21, MUTED)
        self.badge(1300, 60, 240, f"{number} / ÉTUDE R0", BA, "#FFF0DD")

    def finish(self, page_number):
        self.path([(60, 1043), (1540, 1043)], LINE, 1)
        self.text(60, 1075, "Source : schéma intégré R0 du ticket #10 | 14 novembre 2026 | Vue explicative, non fabricable", 16, MUTED)
        self.text(1540, 1075, f"{page_number} / 2", 16, MUTED, False, "end")
        (OUT / f"{self.name}.svg").write_text("\n".join(self.svg + ["</svg>"]), encoding="utf-8")
        self.pdf.showPage()


def connections(pdf):
    p = Page(pdf, "branchements")
    p.header("01", "Les branchements", "Une prise USB, deux prises I2C et deux ports de programmation distincts.")

    # Host and externally powered targets. No power source is invented for a BA/BP.
    p.rect(590, 175, 420, 102, "white", USB)
    p.text(800, 214, "PC / Raspberry Pi", 27, INK, True, "middle")
    p.text(800, 247, "USB : données + alimentation de la carte", 19, MUTED, False, "middle")
    p.path([(800, 277), (800, 333)], USB, 7)
    p.text(824, 308, "1 seul câble USB", 18, USB)

    for x, title, model, programming, color in [
        (60, "BOÎTIER PRINCIPAL", "BP - SC944D", "J33 / BDM", BP),
        (1260, "BOÎTIER SECONDAIRE", "BA - PIC16F946", "Contacts TOP / ICSP", BA),
    ]:
        p.rect(x, 355, 280, 320, "white", LINE)
        p.text(x+140, 391, title, 19, INK, True, "middle")
        p.text(x+140, 425, model, 23, INK, True, "middle")
        p.text(x+140, 488, "Bus I2C", 23, BUS, True, "middle")
        p.text(x+140, 527, "Alimentation existante" if color == BP else "Alimentation par le bus", 18, MUTED, False, "middle")
        p.text(x+140, 552, "indépendante de l'USB" if color == BP else "+15 V, indépendante de l'USB", 17, MUTED, False, "middle")
        p.text(x+140, 620, programming, 19, color, True, "middle")
        p.connector(x+80, 653, 120, 36, 10 if color == BP else 5, color, 2 if color == BP else 1)

    p.rect(420, 350, 760, 370, "#EAF2F7", "#8AAAB9", 22, 3)
    p.connector(750, 333, 100, 34, 4, USB)
    p.text(800, 395, "CARTE INTÉGRÉE ESSENSYS", 24, INK, True, "middle")

    # Logical bus bundle, including copper-only +15 V pass-through.
    p.path([(340, 460), (1260, 460)], BUS, 8)
    p.connector(420, 439, 64, 42, 4, BUS)
    p.connector(1116, 439, 64, 42, 4, BUS)
    p.text(452, 427, "J1 I2C", 19, BUS, True, "middle")
    p.text(1148, 427, "J2 I2C", 19, BUS, True, "middle")
    p.rect(535, 438, 530, 44, "#EAF2F7", "#EAF2F7", 2, 0)
    p.text(800, 465, "SDA / SCL / 0 V / +15 V : traversée", 22, BUS, True, "middle")
    p.text(800, 510, "+15 V non utilisé pour alimenter la carte", 19, MUTED, False, "middle")

    p.rect(475, 535, 310, 92, "white", BUS, 12)
    p.text(630, 572, "Analyseur FX2 intégré", 23, INK, True, "middle")
    p.text(630, 603, "SCL + SDA et 6 voies auxiliaires", 18, MUTED, False, "middle")
    p.rect(815, 535, 310, 92, "white", BP, 12)
    p.text(970, 572, "RP2350 intégré", 23, INK, True, "middle")
    p.text(970, 603, "Programmation BP / BA prévue", 18, MUTED, False, "middle")
    p.text(550, 666, "J_BP / BDM", 21, BP, True, "middle")
    p.text(1050, 666, "J_BA / ICSP", 21, BA, True, "middle")
    p.connector(490, 694, 120, 42, 10, BP, 2)
    p.connector(990, 694, 120, 42, 6, BA)
    p.path([(550, 736), (550, 770), (200, 770), (200, 689)], BP, 6)
    p.path([(1050, 736), (1050, 770), (1400, 770), (1400, 689)], BA, 6, True)
    p.text(365, 803, "Adaptateur BP dédié", 19, BP, True, "middle")
    p.text(1230, 803, "Adaptateur BA dédié, à qualifier", 19, BA, True, "middle")

    cards = [
        (60, "01 / CAPTURE PASSIVE", BUS, "Le bus passe de J1 à J2.\nL'analyseur observe SDA/SCL.\nAucune injection de commande I2C."),
        (565, "02 / PROGRAMMATION", BP, "Un seul port actif à la fois : BP ou BA.\nBP : BDM. BA : ICSP, pas JTAG.\nUF2 actuel : diagnostic uniquement."),
        (1070, "03 / NAPPE FC14P", BA, "14 contacts, femelle/femelle, 1 m.\nAdaptateurs et détrompages à valider.\nAucun branchement direct présumé."),
    ]
    for x, title, color, body in cards:
        p.rect(x, 845, 470, 158, "white", LINE)
        p.text(x+22, 881, title, 19, color, True)
        p.paragraph(x+22, 916, body, 426, 19, leading=28)
    p.text(800, 1027, "Schéma de principe sur banc : niveaux et adaptateurs à qualifier ; 0 V commun avec l'USB.", 18, MUTED, False, "middle")
    p.finish(1)


def board(pdf):
    p = Page(pdf, "implantation-proposee")
    p.header("02", "Le circuit imprimé, vu de dessus", "Implantation proposée des fonctions. Dimensions, empreintes et pistes ne sont pas figées.")
    pcb, silk = "#155C50", "#D8EEE5"
    p.rect(180, 225, 1240, 660, pcb, "#0B3C35", 30, 4)
    for x, y in [(210, 255), (1390, 255), (210, 855), (1390, 855)]:
        p.circle(x, y, 12, BG, "#98BAAA")
    p.text(230, 845, "ESSENSYS  /  R0  /  IMPLANTATION INDICATIVE", 17, silk, True)

    # I2C connectors at the top; this corridor is an allocation, not copper geometry.
    p.connector(360, 207, 170, 58, 4, BUS)
    p.connector(1080, 207, 170, 58, 4, BUS)
    p.text(445, 194, "J1 - I2C ENTRÉE", 21, BUS, True, "middle")
    p.text(1165, 194, "J2 - I2C SORTIE", 21, BUS, True, "middle")
    p.rect(310, 282, 980, 55, "#276B5C", "#79A48F", 10, 1)
    p.text(800, 315, "TRAVERSÉE J1 / J2 : SDA, SCL, 0 V, +15 V", 22, "#F1F6EA", True, "middle")
    p.text(800, 365, "8 ENTRÉES PROTÉGÉES : RÉSISTANCES + SP0502 + SN74LVC2G17", 18, silk, True, "middle")
    for i in range(8):
        x = 360 + i*113
        p.rect(x, 384, 76, 38, "#344943", "#A8C1AE", 4, 1)
        p.text(x+38, 409, ["SCL", "SDA", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8"][i], 17, "#FFFFFF", True, "middle")

    # Internal blocks are packaged shapes, deliberately without fake copper tracks.
    p.rect(156, 490, 70, 74, "#D7E1E5", "#5D7783", 4, 3)
    p.rect(149, 509, 40, 36, "#314652", "#90A3AC", 3)
    p.text(120, 490, "USB", 22, USB, True, "middle")
    p.text(120, 588, "vers PC", 17, USB, False, "middle")
    p.chip(305, 475, 175, 112, "USB2512B", "Hub USB interne")
    p.chip(610, 470, 220, 150, "FX2LP", "Analyseur 8 voies", pins=10)
    p.chip(1010, 470, 195, 150, "RP2350A", "Programmateur", pins=8)
    p.chip(1230, 485, 120, 65, "QSPI", "Flash", pins=4)
    p.rect(515, 510, 67, 40, "#BBC7CB", "#526E79", 6)
    p.text(548, 536, "24 MHz", 13, INK, True, "middle")
    p.rect(900, 510, 75, 40, "#BBC7CB", "#526E79", 6)
    p.text(938, 536, "12 MHz", 13, INK, True, "middle")
    p.text(391, 629, "USB vers FX2 + RP2350", 17, silk, False, "middle")
    p.text(720, 655, "6 points de test auxiliaires", 17, silk, False, "middle")
    for i in range(6):
        p.circle(655+i*26, 676, 5, "#DCC78B")

    p.rect(260, 680, 280, 125, "#276B5C", "#79A48F", 12, 1)
    p.text(400, 708, "ALIMENTATIONS USB", 18, silk, True, "middle")
    for i, title in enumerate(["HUB", "FX2", "RP"]):
        x = 282+i*84
        p.rect(x, 727, 65, 37, "#253D36", "#92B5A3", 4, 1)
        p.text(x+32, 752, title, 16, silk, True, "middle")
    p.text(400, 789, "+15 V exclu de cette zone", 16, silk, False, "middle")

    p.rect(620, 713, 335, 104, "#305A65", "#BEB0DE", 12, 2)
    p.text(787, 744, "INTERFACE BP / BDM", 19, "#FFFFFF", True, "middle")
    p.text(787, 772, "TXU0204 + AND + NMOS", 18, "#E6EAF3", False, "middle")
    p.text(787, 798, "Mesure VREF + retour RESET", 17, "#E6EAF3", False, "middle")
    p.connector(717, 857, 140, 50, 10, BP, 2)
    p.text(787, 938, "J_BP - PROGRAMMATION BP", 20, BP, True, "middle")

    p.rect(1010, 682, 330, 135, "#FFF0DD", BA, 12, 3, True)
    p.text(1175, 716, "RÉSERVE BA / VPP", 22, BA, True, "middle")
    p.text(1175, 748, "Étage à concevoir", 21, BA, True, "middle")
    p.text(1175, 778, "Niveaux 3,3 / 5 V + VPP 10-12 V", 17, BA, False, "middle")
    p.text(1175, 803, "Aucune VPP vers le port BP", 17, BA, False, "middle")
    p.connector(1105, 857, 140, 50, 6, BA)
    p.text(1175, 938, "J_BA - PROGRAMMATION BA", 20, BA, True, "middle")

    p.rect(60, 972, 1480, 54, "white", LINE, 12)
    p.text(800, 1006, "5 prises extérieures. Géométrie symbolique, connecteurs FC14P à adapter. Aucune piste routée, aucun Gerber.", 20, MUTED, False, "middle")
    p.finish(2)


def main():
    pdf_path = OUT / "essensys-branchements-implantation.pdf"
    pdf = canvas.Canvas(str(pdf_path), pagesize=(W, H), invariant=1, pageCompression=1)
    pdf.setTitle("Essensys - Branchements et implantation proposée R0")
    pdf.setAuthor("Essensys")
    pdf.setSubject("Vue de branchement et proposition non fabricable ; aucun PCB routé")
    connections(pdf)
    board(pdf)
    pdf.save()
    for number, name in [(1, "branchements"), (2, "implantation-proposee")]:
        subprocess.run(["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile", "-scale-to", "2200", "-png", str(pdf_path), str(OUT/name)], check=True)
    print(f"Generated 2 SVG, 2 PNG and 1 two-page PDF in {OUT}")


if __name__ == "__main__":
    main()
