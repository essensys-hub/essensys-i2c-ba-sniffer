## Purpose

Étendre la Feature existante avec la carte intégrée du ticket #10 : analyseur
huit voies et processeur RP2350 sur un PCB unique, traversée du bus et programmation
cible. Le BA/PIC reste la cible initiale ; une demande de clarification distingue
BA/ICSP et BP/BDM. L'analyseur externe reste l'oracle de comparaison. L'étude
antérieure à module Pico/PIO est conservée comme prototype, non comme carte finale.

## ADDED Requirements

### Requirement: Traversée indépendante de l'alimentation de la carte

La carte SHALL assurer une liaison cuivre directe SDA/SCL/0 V/+15 V entre les deux
connecteurs du bus. Le +15 V SHALL rester séparé de l'alimentation USB de l’instrument et
des GPIO. Les branches de mesure SHALL être à haute impédance, sans pull-up.

#### Scenario: Instrument hors tension

- **WHEN** l’instrument est éteint, redémarre ou est débranché de l'USB
- **THEN** la continuité des quatre conducteurs subsiste et les limites électriques
  du bus sont respectées sur banc

### Requirement: Analyseur et processeur intégrés

La carte SHALL intégrer un composant d'acquisition huit voies compatible avec
la chaîne sigrok/fx2lafw et le RP2350 directement sur le PCB, avec ses mémoires,
horloges et alimentations nécessaires. Aucun module analyseur ou Pico enfiché
ne SHALL être requis pour le fonctionnement final. La référence FX2LP est une
candidate à vérifier dans la BOM ; le boîtier de référence ne l'identifie pas.

#### Scenario: Utilisation de la carte complète

- **WHEN** l'utilisateur branche l'instrument au PC
- **THEN** acquisition et programmation sont fournies par les composants du même
  PCB ; aucune carte analyseur ni module Pico externe n'est nécessaire

### Requirement: Huit voies synchrones protégées

L'analyseur intégré SHALL capturer huit bits simultanés, bit 0 = CH1/SCL,
bit 1 = CH2/SDA. Toutes les entrées SHALL être tamponnées et protégées ; SDA/SCL
utilisent SN74LVC2G17 et SP0502. Aucune sortie RP2350 ou FX2 ne SHALL piloter le
bus observé. CH3..CH8 SHALL être accessibles sur points de test internes selon
la connectique minimale proposée, à documenter avant schéma final.

#### Scenario: Acquisition et transfert

- **WHEN** une acquisition valide est demandée par l'outillage hôte
- **THEN** fréquence réelle, nombre d'échantillons et erreurs signalées par le
  pilote sont conservés avec le résultat ; un transfert interrompu n'est pas
  déclaré complet
- **AND** les limites de détection des pertes sont documentées et testées sur banc

#### Scenario: Performance déclarée

- **WHEN** les performances sont documentées
- **THEN** limites calculées et limites mesurées du PCB sont distinguées ; le
  marquage 24 MHz du boîtier de référence ne valide pas la bande passante de la carte

### Requirement: Une prise USB pour deux fonctions

L'architecture SHALL proposer une seule prise USB extérieure et un hub USB 2.0
High-Speed interne avec deux périphériques : l'analyseur et le RP2350. Le flux
High-Speed de capture ne SHALL pas traverser le contrôleur USB Full-Speed du
RP2350. Les profils d'alimentation, courants, états suspendus et séquences
d'énumération SHALL être dimensionnés et vérifiés.

#### Scenario: Énumération et capture

- **WHEN** un hôte compatible raccorde le câble USB unique
- **THEN** les deux fonctions sont identifiées et l'analyseur dispose du chemin
  USB High-Speed, sans seconde prise extérieure ni pont de données via le RP2350

### Requirement: Connectique et distinction des protocoles

La connectique extérieure proposée SHALL comprendre l'USB, J1/J2 et une prise de
programmation cible. Son protocole, son brochage et le rôle de la nappe FC14P de
1 m SHALL être figés après clarification BA/ICSP ou BP/BDM. Le brochage IDC14
« huit voies + six masses » de l'étude antérieure ne SHALL pas être présenté
comme un brochage de programmation, ni comme un standard JTAG.

#### Scenario: Port cible non encore défini

- **WHEN** la cible ou son adaptation électrique n'est pas confirmée
- **THEN** le connecteur de programmation reste à définir et aucune compatibilité
  ICSP/BDM, aucune présence de VPP ni liaison numéro à numéro n'est supposée

#### Scenario: Contrôle de câblage

- **WHEN** la nappe et les adaptateurs sont contrôlés hors tension
- **THEN** chaque contact correspond à la table spécifique à la cible, sans
  inversion ; le repère 1 et le protocole sont marqués et vérifiés

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

La qualification SHALL inclure niveaux, montée, huit voies via les accès retenus,
échanges USB des deux fonctions, comparaison à l’analyseur externe, câble de
programmation retenu, VPP et programmation/relecture de chaque variante BA.

#### Scenario: Absence de prototype

- **WHEN** seules les vérifications logicielles et CAO sont disponibles
- **THEN** le ticket et les tâches de banc restent ouverts ; aucune mesure n'est
  remplacée par une estimation ou un résultat simulé
