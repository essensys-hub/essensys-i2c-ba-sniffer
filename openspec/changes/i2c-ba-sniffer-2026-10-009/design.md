## Context

Pour la motivation, voir `proposal.md` (Why). Faits techniques relevés dans le code et qui structurent l'approche :

| Fait | Source |
|---|---|
| Bus `i2c0`, 50 kHz, mode polled, maître SC944D ; station BP `0x10` | `application.h:3,8`, `ba_i2c.c:106-118` |
| Esclaves `0x11 + n` : 0 pièces de vie, 1 chambres, 2 pièces d'eau | `ba_i2c.c:178`, `global.h:462-468` |
| Adresse d'un BA figée à la compilation (`TYPE_*` → `I2C_ADDR`) ; images `.hex` v1.7 vérifiées : `piece vie` 0x11, `piece chambre` 0x12, `piece eau` 0x13 | `hard.h:16-28,240,451`, `hard.c:56` |
| Transaction : `START addr(W)` → N octets → repeated START `addr(R)` → 5 octets → `STOP` ; 100 ms entre transactions | `ba_i2c.c:206-371,508` |
| Codes de trame 1 à 5, longueurs 11/11/19/11/4 ; réponse 5 octets | `global.h:516-522`, `slavenode.c:201-340` |
| CRC-16/MODBUS (init `0xFFFF`, polynôme `0xA001`) | `crc.c` (`us_CalculerCRCSurTrame`) |
| Émission seulement sur changement ; défaut dans l'index 12 après 5 échecs, abandon après 20 ; ensuite, un seul essai par nouvel ordre | `ba.c:171-211,485-510` |
| Profils de sorties : PDV 5 lampes / 3 variateurs / 6 volets ; CHB 7 / 4 / 5 ; PDE 13 / 1 / 4 | `hard.c:107-145` des BA |
| Niveaux 5 V côté BA ; pull-ups d'environ 10 kΩ ; J1/J2 : 1 SDA (RC7), 2 SCL (RC6), 3 0 V, 4 +15 V | `docs/hardware.md:177` (SC944D), `hard.c:54` |

Le change `essensys-i2c-ba-sniffer-2026-07-038` (essensys-memory) contient l'analyse détaillée du protocole et le plan Pico. Celui-ci reste valable pour la phase 2.

## Goals / Non-Goals

**Goals :**
- Un outil assemblable en une journée avec du matériel du commerce, sans développement firmware.
- Un décodeur testable sans matériel (corpus) et identique en direct et en rejeu.
- Une sonde et une procédure qui ne peuvent ni perturber le bus ni créer de pont de masse.

**Non-Goals :**
- La capture autonome ou permanente : c'est le rôle du Pico (038) et de l'ESP32 N2 (008).
- L'analyse électrique fine (niveaux analogiques, temps de montée) : il faut un oscilloscope.
- Toute émission, tout rejeu actif ou toute injection sur le bus ou le backend.
- L'accès direct de l'outil au CM5 : les journaux sont fournis sous forme de fichier.

## Decisions

### D1 — Analyseur FX2 + sigrok en phase 1, Pico en phase 2

**Choix :** analyseur logique USB à base de CY7C68013A (pilote `fx2lafw`), piloté par `sigrok-cli` sur un Raspberry Pi (ou un portable) alimenté sur batterie.

**Pourquoi :** le matériel coûte une dizaine d'euros et sigrok est empaqueté dans Raspberry Pi OS. Son décodeur I2C est éprouvé et sert d'oracle indépendant. Il n'y a aucun firmware à écrire.

**Alternatives écartées :**
- Pico PIO (change 038) : plus intégré, mais demande firmware et validation. Il reste la phase 2.
- Contrôleur I2C du Raspberry Pi (`i2c-dev`) : pas de mode moniteur, risque d'ACK parasite, broches non 5 V-tolérantes.
- GPIO du Pi avec `pigpio` : Linux n'est pas temps réel, les captures sont moins fiables qu'un échantillonnage matériel.
- Module ESP32 N2 : c'est la cible permanente, mais il n'est pas encore fabriqué.

### D2 — Un seul flux brut, partagé entre sigrok et la détection des lignes bloquées

**Choix :** l'acquisition (`sigrok-cli -d fx2lafw -O binary`), ou la relecture d'une capture (`sigrok-cli -i x.sr -O binary`), produit un **flux brut** (un octet par échantillon, bit n = voie Dn). Le décodeur Python :
- l'envoie sur l'entrée standard d'un second `sigrok-cli -I binary -i - -P i2c:scl=…:sda=… -A i2c=… --protocol-decoder-samplenum`, qui fournit les événements I2C avec leurs numéros d'échantillon ;
- le parcourt lui-même avec `bytes.translate` et `bytes.find` pour repérer une ligne SDA ou SCL au niveau bas pendant plus de 10 ms.

Les enregistrements des deux sources sont fusionnés par numéro d'échantillon, derrière un filigrane commun. Le résultat ne dépend ni de la taille des blocs ni du rythme d'arrivée.

**Pourquoi :**
- le direct et le rejeu passent par **exactement** le même code ;
- le décodeur I2C de sigrok reste la seule source bas niveau du protocole (oracle) ;
- les numéros d'échantillon donnent un horodatage déterministe.

**Alternatives écartées :**
- Décodeur `timing` de sigrok pour les lignes bloquées : il donne la durée entre deux fronts mais pas le niveau de la ligne. Il ne distingue donc pas le repos du bus (haut, 100 ms entre transactions) d'une ligne bloquée basse. Écarté après essai.
- Réimplémenter le décodage I2C en Python : cela ferait perdre l'oracle sigrok.

Un décodeur empilé `libsigrokdecode` « essensys », pour afficher le décodage dans PulseView, reste un bonus de phase 2.

### D3 — Décodeur Python, bibliothèque standard uniquement

**Choix :** paquet `essensys_i2c_sniffer` pour Python ≥ 3.11, sans dépendance d'exécution, avec une CLI `essensys-i2c-sniff`. Il est découpé en trois étages purs :
1. événements sigrok → transactions ;
2. transactions → trames validées : identité du BA, longueur, CRC, écho ;
3. trames → commandes observées : profils par type de BA, priorités du firmware BA.

`pytest` est une dépendance de développement seulement.

**Pourquoi :** installation triviale sur un Pi hors ligne, étages testables séparément, sortie NDJSON stable versionnée par `schema`.

### D4 — Sonde : tampon 5 V-tolérant, résistances série, aucune pull-up

**Choix :** petite carte KiCad, ou montage sur plaque à pastilles documenté dans Fritzing :
- connecteur compatible J1/J2 des BA, broche 4 absente ou coupée ;
- résistances série d'environ 1 kΩ sur SDA et SCL, plus une protection ESD de faible capacité ;
- tampon non inverseur `74LVC2G17` alimenté en 3,3 V par l'analyseur (entrées 5,5 V tolérées) ;
- sorties vers les voies D0 (SCL) et D1 (SDA) ;
- 0 V commun bus et analyseur.

**Pourquoi :** la charge sur le bus reste négligeable (entrées CMOS derrière 1 kΩ). La broche +15 V est physiquement exclue. La sonde fonctionne quelle que soit la tolérance d'entrée du clone FX2.

**Alternative écartée :** fils directs vers l'analyseur. Cela dépend de la tolérance 5 V non garantie des clones, et il n'y a aucune protection en cas d'erreur de broche.

### D5 — Isolement : hôte sur batterie, Wi-Fi seulement, ou isolateur USB

**Choix :** la configuration de référence est un Raspberry Pi sur batterie externe, piloté en Wi-Fi, sans câble Ethernet ni chargeur. En variante, un isolateur USB d'au moins 2,5 kV (type ADuM3160) entre l'analyseur et un hôte relié au secteur.

**Pourquoi :** le retex foudre a montré qu'une liaison métallique entre îlots TBTS crée un chemin de courant d'équilibrage à travers le bus. L'outil de debug ne doit pas recréer ce chemin.

### D6 — Corrélation par fichier de journaux, pas d'accès au CM5

**Choix :** l'opérateur exporte les journaux du backend, par exemple `ssh gateway 'docker logs --since 30m essensys-backend'`, vers un fichier. L'outil rapproche ce fichier de la capture par fenêtre temporelle. Les horloges sont recalées au premier `Sending Actions` suivi d'une trame cohérente, ou par un décalage fourni.

**Pourquoi :** l'outil n'a besoin d'aucun identifiant ni d'aucun accès réseau, et ne peut rien envoyer au backend.

### D7 — Documentation dans essensys-doc, schémas versionnés à la source

**Choix :**
- section `docs/debug/` (`index.md`, `espion-i2c.md`) dans essensys-doc ;
- schéma Archify : source JSON versionnée avec la doc, rendu en iframe comme pour le retex foudre et le module N2 ;
- exports Fritzing et KiCad produits dans ce dépôt, sous `hardware/`, et copiés dans `docs/debug/img/` ;
- publication par le rôle Ansible `docs_site` après relecture et fusion.

### D8 — Tests

**Choix :**
- Tests unitaires par étage.
- Tests de non-régression `NR-i2c-ba-sniffer-1` à `-6` sur le corpus de référence :
  1. aucune commande d'émission exposée ;
  2. NACK d'adresse qualifié « BA absent » ;
  3. CRC faux signalé ;
  4. répétitions puis abandon ;
  5. ligne bloquée détectée ;
  6. rejeu identique au direct.
- CI GitHub Actions : `pytest`, plus `kicad-cli sch erc` (et `pcb drc` si un PCB existe) dans une image KiCad.
- Aucun test ne pilote l'armoire. La capture réelle est une observation passive, déclenchée par l'exploitant.

## Risks / Trade-offs

- [Décodeur qui « ment »] → l'oracle bas niveau est le décodeur I2C de sigrok, et le corpus est relu dans PulseView. Toute divergence est un défaut du décodeur jusqu'à preuve du contraire.
- [Ordre des octets du CRC ou des bits ACTIONS mal supposé] → à confirmer sur des trames réellement capturées (tâches dédiées) avant de figer la sortie attendue du corpus.
- [Erreur de branchement sur le +15 V] → broche 4 absente du connecteur de la sonde, contrôle à l'ohmmètre, branchement hors tension.
- [Pont de masse par l'hôte] → configuration sur batterie par défaut, interdiction explicite dans la doc.
- [Capture sur l'installation réelle] → strictement passive, faite par une personne habilitée, et seules les commandes habituelles de l'exploitant sont observées.
- [Débordement USB du FX2 sur un Pi chargé] → 1 MHz est très en dessous de la capacité. Les débordements sont signalés, jamais masqués.
- [Captures publiées] → les trames I2C ne contiennent pas de données personnelles. Les noms de fichiers et les métadonnées sont contrôlés avant publication.

## Migration Plan

Aucune migration : nouvel outil, nouveau dépôt. Pour revenir en arrière, il suffit de retirer la sonde. Le firmware, le backend et la configuration de l'armoire ne sont pas touchés.

Ordre de mise en œuvre :
1. Décodeur et corpus synthétique.
2. Sonde, sur banc.
3. Validation croisée avec PulseView.
4. Capture passive sur l'installation touchée.
5. Documentation et publication.

## Open Questions

- Référence exacte du connecteur J1/J2 des BA, à relire dans la BOM SC940D/SC941C/SC942C. Elle conditionne le connecteur de la sonde, pas les specs.
- PCB fabriqué ou plaque à pastilles pour la première sonde. Les deux satisfont les specs ; la décision se prend à la tâche matérielle.
