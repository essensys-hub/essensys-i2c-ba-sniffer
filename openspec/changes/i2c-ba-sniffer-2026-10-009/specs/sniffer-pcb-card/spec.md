## Purpose

Étendre la Feature existante avec la carte Pico 2 du ticket #10 : analyseur logique
huit voies, traversée du bus et programmateur ICSP des BA. La sonde FX2 reste une
variante indépendante et l'oracle de comparaison.

## ADDED Requirements

### Requirement: Traversée indépendante de l'alimentation du Pico

La carte SHALL assurer une liaison cuivre directe SDA/SCL/0 V/+15 V entre les deux
connecteurs du bus. Le +15 V SHALL rester séparé de l'alimentation USB du Pico et
des GPIO. Les branches de mesure SHALL être à haute impédance, sans pull-up.

#### Scenario: Pico hors tension

- **WHEN** le Pico est éteint, redémarre ou est débranché de l'USB
- **THEN** la continuité des quatre conducteurs subsiste et les limites électriques
  du bus sont respectées sur banc

### Requirement: Huit voies synchrones protégées

La carte SHALL capturer huit bits simultanés par PIO et DMA, bit 0 = CH1/SCL,
bit 1 = CH2/SDA. Toutes les entrées SHALL être tamponnées et protégées ; SDA/SCL
utilisent SN74LVC2G17 et SP0502. Aucune sortie Pico ne SHALL atteindre le bus.
Les sélecteurs de source SHALL éviter de relier une source IDC au bus existant.

#### Scenario: Capture bornée sans dépendance au débit USB

- **WHEN** une acquisition valide est demandée
- **THEN** le Pico remplit un tampon borné avant de transmettre le résultat, avec
  fréquence réelle, nombre d'échantillons, état et contrôle d'intégrité
- **AND** une erreur ou un transfert tronqué est signalé comme échec, jamais succès

#### Scenario: Performance déclarée

- **WHEN** les performances sont documentées
- **THEN** limites calculées et limites mesurées sur le PCB sont distinguées ; le
  marquage 24 MHz du FX2 ne constitue pas une validation du Pico

### Requirement: Nappe FC14P et séparation ICSP

L'analyse SHALL utiliser une embase mâle IDC 2 × 7 détrompée, compatible avec la
nappe Sourcingmap FC14P de 1 m. Les 14 contacts SHALL être documentés avec huit
signaux et six masses. VPP SHALL être absente de ce connecteur. La prise PICkit
six points SHALL être distincte. L'adaptateur 14/10 points du FX2 SHALL être
documenté et contrôlé avant utilisation.

#### Scenario: Contrôle de câblage

- **WHEN** la nappe et les adaptateurs sont contrôlés hors tension
- **THEN** chaque contact correspond à la table publiée, sans inversion ni mise en
  commun de signaux ; le repère de broche 1 est visible

### Requirement: Programmation spécifique PIC16F946

Le programmateur SHALL utiliser le protocole DS41244F, VPP entre 10 et 12 V et
adaptation des niveaux 3,3/5 V. Les configurations des fichiers Intel HEX SHALL
être vérifiées avant toute commande destructive. Les bits CP/CPD, EEPROM et mots
de calibration SHALL faire l'objet d'une politique explicite. Un HEX invalide,
incomplet ou non pris en charge SHALL être refusé avant toute connexion matérielle.

#### Scenario: Configuration des BA v1.7

- **WHEN** les trois images BA v1.7 sont inspectées
- **THEN** le mot brut 0xFFF2 est normalisé en mot PIC 14 bits 0x3FF2 ; MCLRE=1,
  FOSC=2, CP=1 et CPD=1 sont rapportés, sans inventer de bit LVP

#### Scenario: Circuit de reset non qualifié

- **WHEN** la compatibilité du circuit MCLR/NCP803 du BA avec VPP n'est pas établie
- **THEN** le mode programmation sur BA reste indisponible et la fabrication
  définitive du circuit ICSP n'est pas déclarée prête

### Requirement: État inactif et défauts

VPP SHALL être coupée au boot, reset, expiration de commande et défaut. Le mode
capture SHALL interdire les commandes ICSP. Les tests SHALL utiliser un banc
isolé ; aucune armoire réelle ne SHALL être pilotée.

#### Scenario: Défaut pendant la programmation

- **WHEN** l'hôte disparaît ou une tension cible sort de la plage autorisée
- **THEN** VPP est coupée, les sorties ICSP deviennent inactives et l'erreur est
  rapportée ; la vérification ne peut pas être marquée réussie

### Requirement: Conception et fabrication reproductibles

Les sources KiCad, règles JLCPCB, nets attendus et scripts SHALL être versionnés.
La CI SHALL contrôler ERC, DRC et netlist sans masquer les violations. Les exports
Gerber/perçages/BOM/CPL SHALL correspondre au PCB validé ; la BOM SHALL identifier
fabricant, référence LCSC, pièces assemblées et pièces manuelles.

#### Scenario: Préparation de fabrication

- **WHEN** le dossier de fabrication est généré
- **THEN** ses contrôles automatiques sont archivés et son statut distingue
  prototype non validé et matériel qualifié ; la commande reste à l'utilisateur

### Requirement: Validation physique séparée des tests logiciels

La qualification SHALL inclure niveaux, montée, huit voies sur nappe 1 m,
comparaison FX2, VPP et programmation/relecture de chaque variante BA.

#### Scenario: Absence de prototype

- **WHEN** seules les vérifications logicielles et CAO sont disponibles
- **THEN** le ticket et les tâches de banc restent ouverts ; aucune mesure n'est
  remplacée par une estimation ou un résultat simulé
