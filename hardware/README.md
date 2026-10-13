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

Le schéma KiCad (`kicad/export/sonde-i2c-passive.png`) se lit de gauche à droite : SCL sur la rangée du haut, SDA sur celle du bas.

```
BA J1/J2      sonde                                                   J2 (vers l'analyseur et le Pi)
 2 SCL ──[R2 1 kΩ]──┬── R4 1 MΩ → 0 V ── D1 ── U1A (1→6) ───────────► 2 SCL → D0
 1 SDA ──[R1 1 kΩ]──┬── R3 1 MΩ → 0 V ── D1 ── U1B (3→4) ───────────► 3 SDA → D1
 3 0 V ──────────────────────────────────────────────────────────────► 4 0 V → GND analyseur + broche 9 du GPIO
 4 +15 V (position vide, aucun contact)                  U1 VCC + C1 ◄── 1 +3,3 V ← broche 1 du GPIO du Pi
```

Ni pull-up ni alimentation ne sont prélevées sur le bus. Le 74LVC2G17 accepte 5,5 V en entrée sous 3,3 V, même non alimenté (Ioff). Le 0 V de la sonde est celui de l'armoire : l'hôte (analyseur et Pi) reste sur batterie, sans Ethernet ni chargeur secteur.

## Réalisation : plaque à pastilles (tâche 5.3)

Décision du 2026-10-13 : la première sonde est câblée sur une **plaque à pastilles**, sans circuit imprimé. Un PCB pourra suivre.

- D1 (SP0502BAHT, SOT-23) se monte sur un adaptateur SOT-23 vers SIP3.
- U1 (74LVC2G17, SC-70-6) se monte sur un adaptateur SC-70 vers DIP6.

| Repère | Valeur | Rôle |
|---|---|---|
| J1 | Boîtier WR-MPC3 2×2 + 3 contacts sertis | Câble vers J1/J2 du BA (position 4 vide) |
| R1, R2 | 1 kΩ | Résistances série SDA et SCL |
| R3, R4 | 1 MΩ | Rappel au 0 V si la sonde est débranchée (5 µA sous 5 V) |
| D1 | SP0502BAHT | Protection ESD 2 voies, 5,5 V |
| U1 | 74LVC2G17 | Tampon tolérant au 5 V, alimenté en 3,3 V |
| C1 | 100 nF | Découplage de U1 |
| J2 | Barrette 1×4 | 1 +3,3 V, 2 SCL vers D0, 3 SDA vers D1, 4 0 V |

## Fichiers

| Fichier | Contenu | Régénération |
|---|---|---|
| `kicad/sonde-i2c-passive.kicad_sch` | Schéma câblé, outils KiCad 10 (ERC : 0 erreur, 0 avertissement) | `python3 hardware/kicad/gen_sch.py` |
| `kicad/check_netlist.py` | Vérifie que la netlist exportée correspond au circuit voulu (lancé en CI) | `kicad-cli sch export netlist --format kicadsexpr -o sonde.net …` puis `python3 hardware/kicad/check_netlist.py sonde.net` |
| `kicad/export/` | PDF, SVG, PNG recadré et nomenclature CSV | `kicad-cli sch export pdf/svg/bom` |
| `fritzing/sonde-i2c-passive-implantation.fzz` | Plan d'implantation sur plaque à pastilles : repères, valeurs, jonctions soudées, croisements isolés signalés | `python3 hardware/fritzing/gen_fzz.py` |
| `fritzing/sonde-i2c-passive-ensemble.fzz` | Montage d'ensemble : BA, câble, sonde, analyseur FX2, Raspberry Pi sur batterie, câble USB, masse commune | idem |
| `fritzing/export/` | Vues platine exportées par Fritzing (SVG, PNG) | `Fritzing -svg <dossier contenant les .fzz>` |

Les deux croquis Fritzing embarquent leurs pièces, dessinées par le générateur ; seul le Raspberry Pi 3 est une pièce de base de Fritzing. Les pièces sont désignées par leur `moduleIdRef`, sans chemin local.
