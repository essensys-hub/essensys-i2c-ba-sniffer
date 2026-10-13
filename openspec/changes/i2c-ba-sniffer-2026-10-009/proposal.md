## Why

Après le remplacement du BP et du SC940D sur l'installation touchée par la foudre du 9 août 2026, le BP reçoit et acquitte toutes les commandes du CM5. Le BA pièces de vie (0x11) exécute les siennes, mais les BA chambres (0x12) et pièces d'eau (0x13) restent muets : l'index 12 vaut 0x18.

Le firmware BP acquitte `/api/done` **avant** l'envoi I2C, puis abandonne l'ordre sans le signaler après 20 essais. Aucun outil ne montre ce qui passe réellement sur le bus. On ne peut donc pas distinguer :
- un BA absent (NACK sur l'adresse) ;
- une trame corrompue (écho CRC faux) ;
- un bus bloqué ;
- une trame jamais émise.

Le change `essensys-i2c-ba-sniffer-2026-07-038` (essensys-memory) prévoit un espion sur Raspberry Pi Pico, mais il demande du développement firmware et n'a pas commencé. Le besoin est immédiat. Ce change livre un outil utilisable avec du matériel du commerce : un analyseur logique USB et `sigrok-cli`, avec un décodeur Python spécifique au protocole Essensys. La capture Pico reste la phase 2. Le module ESP32 de la carte N2 (`n2-esp32-spy-alarm-2026-10-008`) reste la version permanente.

Ticket : [essensys-hub/essensys-feature-lifecycle#29](https://github.com/essensys-hub/essensys-feature-lifecycle/issues/29).

## What Changes

- **Capture passive par sigrok.** Analyseur logique USB (pilote `fx2lafw`) piloté par `sigrok-cli` sur un Raspberry Pi alimenté sur batterie (ou un portable sur batterie).
  - Le décodeur lit la sortie du décodeur de protocole I2C de sigrok, en direct (flux) ou en rejeu (session `.sr`).
  - Il ne pilote jamais le bus.
- **Décodeur Python du protocole Essensys.** Il :
  - reconstruit les transactions (START, adresse et sens, ACK/NACK, repeated START, 5 octets lus, STOP) ;
  - résout l'identité du BA (0x11 / 0x12 / 0x13) ;
  - valide la longueur attendue pour chaque code de trame (1 à 5) ;
  - vérifie le CRC-16/MODBUS et l'écho de réponse ;
  - détecte les répétitions, les abandons, les NACK d'adresse et les lignes bloquées.

  Règles reprises du change 038 et corrigées sur le code : profils de sorties par type de BA, CRC confirmé dans `crc.c`.
- **Sémantique domotique.** Lampes, variateurs, volets et drapeaux ACTIONS, présentés comme des *commandes observées*, jamais comme des sorties commutées.
- **Restitution.** Sortie lisible et NDJSON, enregistrement et rejeu, et corrélation avec les journaux du backend CM5 (`Sending Actions`, `Action acknowledged`).
- **Sonde passive.** Trois fils (SDA, SCL, 0 V) sur J1/J2 d'un BA, entrées tolérantes au 5 V, aucune pull-up ajoutée, jamais le +15 V. Isolement galvanique (batterie ou isolateur USB) pour ne pas créer de pont de masse entre îlots TBTS.
  - Sources **KiCad** (schéma de l'adaptateur) et **Fritzing** (câblage réel) versionnées.
- **Documentation publique** : nouvelle section **Debug** dans essensys-doc (`https://www.essensys.fr/docs/debug/`). Elle couvre la fabrication de l'outil, la sécurité, le mode opératoire et la lecture des captures, avec un schéma **Archify** de la chaîne de debug, puis elle est publiée par le rôle `docs_site`.
- **Corpus de captures de référence** et tests unitaires sans armoire, plus des tests de non-régression `NR-i2c-ba-sniffer-*`.

## Capabilities

### New Capabilities
- `sigrok-capture` : acquisition passive par analyseur logique et sigrok (configuration, direct ou rejeu), détection électrique logique (NACK d'adresse, ligne bloquée, trame tronquée), garantie de non-émission.
- `i2c-frame-decode` : reconstruction des transactions BP↔BA, identité des BA, longueurs par code de trame, CRC-16, écho de réponse, répétitions et abandons, rejeu identique au direct.
- `ba-event-semantics` : traduction des trames en commandes observées, avec les profils de sorties par type de BA, les règles de priorité du firmware BA et les drapeaux ACTIONS.
- `debug-tooling` : CLI, sortie texte et NDJSON, enregistrement, corrélation avec les journaux du backend CM5, corpus de référence.
- `sniffer-probe-hardware` : sonde passive à trois fils, compatibilité 5 V, isolement, sources KiCad et Fritzing.
- `debug-documentation` : section `docs/debug/` d'essensys-doc, schéma Archify, règles de sécurité et publication.

### Modified Capabilities
_Aucune : le dépôt est nouveau. Le firmware BP, le firmware BA, le backend et le protocole HTTP legacy ne changent pas._

## Impact

- **Nouveau dépôt** `essensys-hub/essensys-i2c-ba-sniffer` (public) :
  - `decoder/` : paquet Python ;
  - `tests/` et `captures/` : tests unitaires et corpus ;
  - `hardware/kicad/` et `hardware/fritzing/` : sources de la sonde ;
  - `docs/` ;
  - `features/` : manifeste.
- **essensys-doc** : nouvelle section `docs/debug/` (navigation mkdocs) et schéma Archify. Lien depuis `install/ajout-bp.md` et `install/remise-en-service-surtension.md`.
- **essensys-memory** : page wiki de l'outil. Le change 038 est noté comme phase 2 (Pico).
- **Dépendances** : `sigrok-cli` et `sigrok-firmware-fx2lafw` (paquets Debian/Raspberry Pi OS), Python ≥ 3.11 sans dépendance native obligatoire, KiCad 9, Fritzing.
- **Sécurité des personnes et du matériel** : branchement hors tension par une personne habilitée, aucune émission sur le bus, aucun pont de masse. Les essais sur l'installation réelle sont **uniquement passifs** : les commandes sont déclenchées par l'exploitant depuis l'interface habituelle, jamais par l'outil ni par les tests.
- **Aucun changement** sur les firmwares SC944D et BA, le backend, le protocole legacy IoT ou le Project #6.
