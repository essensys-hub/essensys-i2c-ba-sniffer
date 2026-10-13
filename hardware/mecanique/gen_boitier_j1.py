#!/usr/bin/env python3
"""Boîtier enfichable imprimable pour l'embase J1/J2 des BA (WR-MPC3 2×2).

Le boîtier se branche sur l'embase mâle Würth 66200421122 d'un BA et ne porte
que trois contacts : 1 SDA, 2 SCL, 3 0 V. La position 4 (+15 V) est borgne :
la broche y entre, mais aucun contact ne peut y être logé, ni par l'avant ni
par l'arrière.

Contacts : femelles « Dupont » 2,54 mm (pour broche carrée de 0,64 mm), par
exemple retirés des fils fournis avec l'analyseur. La cote du logement est un
paramètre (``--contact``) : imprimer d'abord ``calibre-contacts.step`` pour la
choisir.

Usage :
    uv run --no-project --python 3.12 --with cadquery python hardware/mecanique/gen_boitier_j1.py [--rendu]
    # contrôle supplémentaire contre le modèle 3D d'origine de l'embase, recentré :
    ... gen_boitier_j1.py --entete J1_centre.step --decalage-y -0.39
"""

from __future__ import annotations

import argparse
import math
import pathlib

import cadquery as cq

OUT = pathlib.Path(__file__).resolve().parent

# --- Embase du BA, cotes relevées sur le modèle 3D de la carte SC940D --------
# Repère : origine au centre du réseau de broches, z = 0 sur le circuit imprimé.
# y > 0 : rangée 1-2 ; y < 0 : rangée 3-4 et rampe de verrouillage.
# Numérotation et nets confirmés dans SI940D.PcbDoc : 3 = GNDBUS, 4 = +VBUS.
BROCHES = {1: (-1.5, 1.5), 2: (1.5, 1.5), 3: (-1.5, -1.5), 4: (1.5, -1.5)}
CORPS_DEMI = 3.43          # corps de l'embase : carré de 6,86 mm
Z_HAUT = 9.30              # face supérieure de l'embase
Z_FOND = 2.95              # fond des logements
Z_SOCLE = 1.19             # dessous du corps (plots d'appui exclus)
LOGEMENT_DEMI = 1.31       # logements de 2,62 mm
LOGEMENT_CHANFREIN = 0.70  # coin abattu qui sert de détrompeur
COIN = {1: (-1, 1), 2: (1, 1), 3: (1, 1), 4: (-1, 1)}  # coin abattu (signe x, signe y)
BROCHE = 0.64
Z_BROCHE = 7.10
RAMPE_DEMI = 0.75
RAMPE_YZ = [(-3.43, 5.81), (-4.08, 6.41), (-4.73, 6.35), (-4.73, 7.44), (-3.43, 9.30)]
NERVURES = [(-1.70, -0.45), (0.45, 1.70)]  # côté y > 0, de z = 1,5 à 7,9

# --- Boîtier -----------------------------------------------------------------
JEU = 0.15                 # jeu latéral (impression résine)
Z_PIED = Z_FOND + 0.30     # bas des tours, 0,3 mm au-dessus du fond
H_CORPS = 7.0
Z_TETE = Z_HAUT + H_CORPS
PAROI_AVANT = 0.5          # devant du contact, percé pour la broche
ENTREE = 1.0               # passage de broche (0,64 mm + marge)
LOGEMENT_SERTI = 2.3       # au-dessus de l'embase : place pour le sertissage
CAPOT_EP = 1.0
CAPOT_MARGE = 0.6          # paroi autour du capot
CAPOT_JEU = 0.1
CAPOT_DETROMPEUR = 1.0     # coin abattu côté broche 4
FIL = 1.8                  # trous de sortie des fils
BRAS_DEMI = 1.6
BRAS_EP = 0.9
Z_BRAS_BAS = 5.20
Y_BRAS_INT = RAMPE_YZ[2][0] - JEU            # -4,88
Y_BRAS_EXT = Y_BRAS_INT - BRAS_EP           # -5,78
Y_ERGOT = -4.20                              # bord intérieur de l'ergot
Z_ERGOT = 6.15                               # sous la rampe (6,35 à 6,41)


def polygone(cx, cy, demi, coin=None, chanfrein=0.0):
    """Carré centré, avec un coin abattu à 45° (sommets dans le sens direct)."""
    sommets = [(cx - demi, cy - demi), (cx + demi, cy - demi), (cx + demi, cy + demi), (cx - demi, cy + demi)]
    if not coin:
        return sommets
    cible = (cx + coin[0] * demi, cy + coin[1] * demi)
    out = []
    for i, s in enumerate(sommets):
        if s != cible:
            out.append(s)
            continue
        for voisin in (sommets[i - 1], sommets[(i + 1) % 4]):
            dx, dy = voisin[0] - s[0], voisin[1] - s[1]
            n = math.hypot(dx, dy)
            out.append((s[0] + dx / n * chanfrein, s[1] + dy / n * chanfrein))
    return out


def prisme(points, z0, z1):
    return cq.Workplane("XY").workplane(offset=z0).polyline(points).close().extrude(z1 - z0)


def pave(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0, centered=False).translate((x0, y0, z0))


def profil_yz(points, demi_x):
    """Prisme d'un profil (y, z) extrudé de -demi_x à +demi_x."""
    wp = cq.Workplane("YZ").workplane(offset=-demi_x).polyline(points).close()
    return wp.extrude(2 * demi_x)


def entonnoir(cx, cy, z0):
    """Entrée de broche : cône carré de 1,5 à 1,0 mm, sur 0,25 mm."""
    bas = cq.Workplane("XY").workplane(offset=z0).center(cx, cy).rect(1.5, 1.5)
    return bas.workplane(offset=0.25).rect(ENTREE, ENTREE).loft()


def boitier(contact: float) -> cq.Workplane:
    corps = pave(-CORPS_DEMI, CORPS_DEMI, -CORPS_DEMI, CORPS_DEMI, Z_HAUT, Z_TETE).edges("|Z").fillet(0.4)
    for n, (cx, cy) in BROCHES.items():
        tour = cq.Workplane("XY").workplane(offset=Z_PIED).polyline(
            polygone(cx, cy, LOGEMENT_DEMI, COIN[n], LOGEMENT_CHANFREIN)).close().offset2D(-JEU, "intersection")
        tour = tour.extrude(Z_HAUT - Z_PIED).faces("<Z").edges().chamfer(0.25)
        corps = corps.union(tour)
    # verrou : bras souple accroché en tête, ergot sous la rampe, languette de déverrouillage
    corps = corps.union(pave(-BRAS_DEMI, BRAS_DEMI, Y_BRAS_EXT, Y_BRAS_INT, Z_BRAS_BAS, Z_TETE))
    corps = corps.union(pave(-BRAS_DEMI, BRAS_DEMI, Y_BRAS_EXT, -CORPS_DEMI + 0.4, Z_TETE - 1.2, Z_TETE))
    corps = corps.union(profil_yz([(Y_BRAS_INT, Z_BRAS_BAS), (Y_ERGOT - 0.30, Z_BRAS_BAS), (Y_ERGOT, Z_BRAS_BAS + 0.30),
                                   (Y_ERGOT, Z_ERGOT), (Y_BRAS_INT, Z_ERGOT)], BRAS_DEMI))
    corps = corps.union(pave(-BRAS_DEMI, BRAS_DEMI, Y_BRAS_EXT - 0.8, Y_BRAS_EXT, Z_BRAS_BAS, Z_BRAS_BAS + 1.0))
    # logements des contacts 1 à 3
    for n in (1, 2, 3):
        cx, cy = BROCHES[n]
        corps = corps.cut(entonnoir(cx, cy, Z_PIED))
        corps = corps.cut(pave(cx - ENTREE / 2, cx + ENTREE / 2, cy - ENTREE / 2, cy + ENTREE / 2, Z_PIED, Z_PIED + PAROI_AVANT + 0.01))
        corps = corps.cut(prisme(polygone(cx, cy, contact / 2, COIN[n], 0.2), Z_PIED + PAROI_AVANT, Z_HAUT))
        d = LOGEMENT_SERTI / 2
        corps = corps.cut(pave(cx - d, cx + d, cy - d, cy + d, Z_HAUT, Z_TETE))
    # position 4 : passage borgne pour la broche, fermé au-dessus
    cx, cy = BROCHES[4]
    corps = corps.cut(entonnoir(cx, cy, Z_PIED))
    corps = corps.cut(pave(cx - ENTREE / 2, cx + ENTREE / 2, cy - ENTREE / 2, cy + ENTREE / 2, Z_PIED, Z_BROCHE + 0.6))
    # logement du capot, coin abattu côté broche 4
    d = CORPS_DEMI - CAPOT_MARGE
    corps = corps.cut(prisme(polygone(0, 0, d, (1, -1), CAPOT_DETROMPEUR), Z_TETE - CAPOT_EP, Z_TETE + 1))
    return corps


def capot() -> cq.Workplane:
    """Capot arrière à coller : bloque les contacts et ferme la position 4."""
    d = CORPS_DEMI - CAPOT_MARGE - CAPOT_JEU
    c = prisme(polygone(0, 0, d, (1, -1), CAPOT_DETROMPEUR + CAPOT_JEU), Z_TETE - CAPOT_EP, Z_TETE)
    for n in (1, 2, 3):
        cx, cy = BROCHES[n]
        c = c.cut(cq.Workplane("XY").workplane(offset=Z_TETE - CAPOT_EP - 1).center(cx, cy).circle(FIL / 2).extrude(CAPOT_EP + 2))
    # marques gravées : croix sur la position 4, flèche vers le fil 1
    cx, cy = BROCHES[4]
    for angle in (45, -45):
        barre = cq.Workplane("XY").workplane(offset=Z_TETE - 0.3).center(cx, cy).rect(1.8, 0.3).extrude(1).rotate((cx, cy, 0), (cx, cy, 1), angle)
        c = c.cut(barre)
    fleche = cq.Workplane("XY").workplane(offset=Z_TETE - 0.3).polyline([(-0.62, 0.62), (0.05, 0.32), (-0.32, -0.05)]).close().extrude(1)
    c = c.cut(fleche)
    return c


def calibre() -> cq.Workplane:
    """Plaquette d'essai : logements de 1,5 à 1,8 mm, repérés par 1 à 4 points."""
    cotes = [1.5, 1.6, 1.7, 1.8]
    p = pave(0, 16, 0, 7, 0, 7)
    for i, s in enumerate(cotes):
        x = 2.5 + i * 3.7
        p = p.cut(pave(x - s / 2, x + s / 2, 2.5 - s / 2, 2.5 + s / 2, -1, 8))
        for k in range(i + 1):
            p = p.cut(cq.Workplane("XY").workplane(offset=6.7).center(x - 0.5 * i + k * 1.0, 5.5).circle(0.3).extrude(1))
    return p


def embase() -> cq.Workplane:
    """Embase simplifiée, reconstruite depuis les cotes ci-dessus (contrôle d'interférence)."""
    e = pave(-CORPS_DEMI, CORPS_DEMI, -CORPS_DEMI, CORPS_DEMI, Z_SOCLE, Z_HAUT)
    for n, (cx, cy) in BROCHES.items():
        e = e.cut(prisme(polygone(cx, cy, LOGEMENT_DEMI, COIN[n], LOGEMENT_CHANFREIN), Z_FOND, Z_HAUT + 1))
    e = e.union(profil_yz(RAMPE_YZ, RAMPE_DEMI))
    for x0, x1 in NERVURES:
        e = e.union(pave(x0, x1, CORPS_DEMI - 0.01, CORPS_DEMI + 0.51, 1.5, 7.9))
    for cx, cy in BROCHES.values():
        e = e.union(pave(cx - BROCHE / 2, cx + BROCHE / 2, cy - BROCHE / 2, cy + BROCHE / 2, -3.1, Z_BROCHE))
    return e


def interference(a: cq.Workplane, b: cq.Shape | cq.Workplane) -> float:
    sb = b.val() if isinstance(b, cq.Workplane) else b
    return a.val().intersect(sb).Volume()


def rendu(b, c, e, chemin: pathlib.Path) -> None:
    """Planche de trois vues ombrées (VTK hors écran), pour la documentation."""
    import vtk

    def acteur(forme, couleur, dz=0.0):
        pd = forme.val().translate(cq.Vector(0, 0, dz)).toVtkPolyData(0.01, 0.1)
        normales = vtk.vtkPolyDataNormals()
        normales.SetInputData(pd)
        normales.SetFeatureAngle(30)
        m = vtk.vtkPolyDataMapper()
        m.SetInputConnection(normales.GetOutputPort())
        a = vtk.vtkActor()
        a.SetMapper(m)
        a.GetProperty().SetColor(*couleur)
        a.GetProperty().SetSpecular(0.3)
        return a

    orange, bleu, gris = (0.95, 0.55, 0.12), (0.25, 0.48, 0.85), (0.22, 0.22, 0.24)
    vues = [
        ([acteur(b, orange)], (30, -45, -25), "Boîtier vu de dessous : tours, entrées, verrou"),
        ([acteur(b, orange), acteur(c, bleu, dz=6)], (25, -40, 45), "Capot à coller : fils 1-2-3, croix = position 4"),
        ([acteur(e, gris), acteur(b, orange), acteur(c, bleu)], (35, -55, 30), "Enfiché sur l'embase J1/J2 du BA"),
    ]
    fenetre = vtk.vtkRenderWindow()
    fenetre.SetOffScreenRendering(1)
    fenetre.SetSize(2100, 700)
    for i, (acteurs, position, titre) in enumerate(vues):
        r = vtk.vtkRenderer()
        r.SetViewport(i / 3, 0, (i + 1) / 3, 1)
        r.SetBackground(1, 1, 1)
        for a in acteurs:
            r.AddActor(a)
        texte = vtk.vtkTextActor()
        texte.SetInput(titre)
        texte.GetTextProperty().SetFontSize(22)
        texte.GetTextProperty().SetColor(0.1, 0.1, 0.1)
        texte.SetPosition(15, 660)
        r.AddViewProp(texte)
        cam = r.GetActiveCamera()
        cam.SetFocalPoint(0, 0, 8)
        cam.SetPosition(*position)
        cam.SetViewUp(0, 0, 1)
        cam.SetParallelProjection(1)
        r.ResetCamera()
        cam.Zoom(0.95)
        fenetre.AddRenderer(r)
    fenetre.Render()
    image = vtk.vtkWindowToImageFilter()
    image.SetInput(fenetre)
    png = vtk.vtkPNGWriter()
    png.SetFileName(str(chemin))
    png.SetInputConnection(image.GetOutputPort())
    png.Write()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--contact", type=float, default=1.70, help="côté du logement de contact, en mm (défaut 1,70)")
    ap.add_argument("--entete", help="STEP de l'embase d'origine, pour un contrôle d'interférence supplémentaire")
    ap.add_argument("--decalage-y", type=float, default=0.0, help="décalage y à appliquer à --entete")
    ap.add_argument("--rendu", action="store_true", help="régénérer export/boitier-j1-vues.png")
    args = ap.parse_args()

    b, c, e = boitier(args.contact), capot(), embase()
    for nom, piece in (("boîtier", b), ("capot", c)):
        v = interference(piece, e)
        print(f"interférence {nom} / embase simplifiée : {v:.4f} mm³")
        assert v < 1e-3, f"{nom} en interférence avec l'embase"
    # l'ergot doit accrocher : remonté de 0,5 mm, il touche la rampe
    accroche = interference(b.translate((0, 0, 0.5)), profil_yz(RAMPE_YZ, RAMPE_DEMI))
    print(f"recouvrement ergot / rampe, boîtier tiré de 0,5 mm : {accroche:.4f} mm³")
    assert accroche > 0.01, "l'ergot n'accroche pas la rampe"
    if args.entete:
        ref = cq.importers.importStep(args.entete).val().translate(cq.Vector(0, args.decalage_y, 0))
        for nom, piece in (("boîtier", b), ("capot", c)):
            print(f"interférence {nom} / modèle d'origine : {interference(piece, ref):.4f} mm³")

    cq.exporters.export(b, str(OUT / "boitier-j1-wr-mpc3.step"))
    cq.exporters.export(c, str(OUT / "boitier-j1-wr-mpc3-capot.step"))
    cq.exporters.export(calibre(), str(OUT / "calibre-contacts.step"))
    ens = (cq.Assembly(name="boitier-j1-sur-embase")
           .add(e, name="embase-BA-simplifiee", color=cq.Color(0.15, 0.15, 0.15))
           .add(b, name="boitier", color=cq.Color(0.95, 0.55, 0.10))
           .add(c, name="capot", color=cq.Color(0.20, 0.45, 0.85)))
    ens.save(str(OUT / "boitier-j1-wr-mpc3-assemblage.step"))
    print("écrit :", ", ".join(p.name for p in sorted(OUT.glob("*.step"))))
    if args.rendu:
        (OUT / "export").mkdir(exist_ok=True)
        rendu(b, c, e, OUT / "export" / "boitier-j1-vues.png")
        print("écrit : export/boitier-j1-vues.png")


if __name__ == "__main__":
    main()
