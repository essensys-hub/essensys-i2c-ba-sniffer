# Sonde passive : matériel

> ⚠️ Branchement et débranchement **hors tension**, par une personne habilitée. Trois fils seulement (SDA, SCL, 0 V), **jamais le +15 V**. Aucun pont de masse : hôte sur batterie, en Wi-Fi seulement, ou isolateur USB.

## Connecteur du bus sur les BA (tâche 5.1)

| Élément | Valeur | Source |
|---|---|---|
| Repères | J1, J2 (chaînage du bus, entrée et sortie) | BOM SC942C (`BOM_[No Variations].csv`) |
| Type | Embase **Micro Mate-N-Lok**, 2 × 2 points, pas de 3 mm, droite, contacts étamés, 250 V / 5 A | BOM SC942C : `MICRO-MATE-N-LOK_WURTH_2X02_D` |
| Brochage | 1 SDA (RC7 du PIC), 2 SCL (RC6), 3 0 V du bus, 4 +15 V (BA_ALIM) | `essensys-board-SC944D/docs/hardware.md:177`, `hard.c:54` des BA |
| Point de piquage conseillé | Connecteur libre du BA en bout de chaîne (SC940D sur l'installation de référence) | photos du retour d'expérience foudre |

**À confirmer (tâche 5.1)**, par recoupement avec une photo de la carte, floutée si elle est publiée :
- famille exacte du boîtier mâle à utiliser côté sonde : TE Micro MATE-N-LOK ou équivalent Würth / Micro-Fit 3.0 ;
- détrompeur et numérotation des broches vue côté câble.

La sonde utilise un boîtier à 4 positions dans lequel **seuls les contacts 1, 2 et 3 sont sertis**. La position 4 (+15 V) reste vide, ce qui exclut mécaniquement le +15 V.

## Schéma de principe

```
BA J1/J2          sonde                                     analyseur FX2
 1 SDA ──[1 kΩ]──┬──────────────► 74LVC2G17 (A2→Y2) ──────► D1 (SDA)
                 └─ ESD faible capacité vers 0 V
 2 SCL ──[1 kΩ]──┬──────────────► 74LVC2G17 (A1→Y1) ──────► D0 (SCL)
                 └─ ESD faible capacité vers 0 V
 3 0 V ───────────────────────────── 0 V ───────────────────► GND
 4 +15 V   (position vide, aucun contact)
                              VCC 74LVC2G17 = 3,3 V fourni par l'analyseur
```

Ni pull-up ni alimentation ne sont prélevées sur le bus. Le 74LVC2G17 accepte 5,5 V en entrée lorsqu'il est alimenté en 3,3 V.

Les sources KiCad (`kicad/`) et Fritzing (`fritzing/`) viennent avec les tâches 5.2 à 5.4.
