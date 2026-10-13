## Purpose

Définir la sonde matérielle qui relie l'analyseur logique au bus I2C de l'armoire. Elle doit rester passive, tolérer le 5 V et ne jamais relier électriquement deux îlots TBTS, conformément aux leçons de l'incident foudre du 9 août 2026.

## ADDED Requirements

### Requirement: Raccordement à trois fils, sans +15 V

La sonde SHALL se raccorder uniquement à SDA, SCL et 0 V du bus :
- J1-1 ou J2-1 : SDA ;
- J1-2 ou J2-2 : SCL ;
- J1-3 ou J2-3 : 0 V.

Elle SHALL ne comporter aucun contact vers J1-4 ou J2-4 (+15 V). Son connecteur SHALL rendre mécaniquement impossible le raccordement de la 4e broche.

#### Scenario: Broche +15 V non raccordée

- **WHEN** on contrôle la sonde à l'ohmmètre, hors tension
- **THEN** aucune continuité n'existe entre la position de broche 4 du connecteur et un fil de la sonde

### Requirement: Entrées 5 V-tolérantes et haute impédance

Les entrées de la sonde SHALL supporter 5,5 V en permanence. Elles SHALL présenter une haute impédance au bus et SHALL ne comporter aucune pull-up. Si l'analyseur n'est pas 5 V-tolérant, la sonde SHALL interposer un tampon non inverseur 5 V-tolérant alimenté côté analyseur.

#### Scenario: Niveaux du bus non dégradés

- **WHEN** la sonde est raccordée au bus d'un banc à 50 kHz
- **THEN** le niveau bas mesuré au BP et au BA, ainsi que le temps de montée, restent dans les tolérances du change i2c-surge-protection-2026-10-007 (niveau bas MCF < 0,85 V, PIC < 1,2 V, montée < 4 µs)

### Requirement: Aucun pont de masse

La chaîne sonde, analyseur et hôte SHALL être isolée galvaniquement du PE et de tout autre îlot pendant une capture sur une installation en service. Deux moyens sont admis : hôte sur batterie sans liaison filaire, ou isolateur USB de 2,5 kV au moins.

#### Scenario: Hôte sur batterie

- **WHEN** la capture est faite avec un Raspberry Pi ou un portable alimenté sur batterie, en Wi-Fi seulement
- **THEN** la documentation interdit tout câble Ethernet, chargeur secteur ou liaison USB vers un équipement relié au PE pendant la capture

### Requirement: Sources de conception versionnées

Le dépôt SHALL contenir :
- le schéma KiCad de la sonde, avec un ERC sans erreur ;
- le PCB s'il est fabriqué, avec un DRC sans erreur ;
- le câblage Fritzing (`.fzz`) de la chaîne BA → sonde → analyseur → hôte.

Il SHALL aussi contenir leurs exports en SVG ou PNG utilisés par la documentation.

#### Scenario: Contrôles KiCad

- **WHEN** la CI exécute `kicad-cli sch erc`, et `pcb drc` si un PCB existe
- **THEN** aucune erreur n'est remontée
