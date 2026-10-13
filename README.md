# essensys-i2c-ba-sniffer

Espion I2C **strictement passif** du bus interne de l'armoire Essensys : boîtier principal SC944D (maître) ↔ boîtiers auxiliaires SC940D (`0x11`), SC942C (`0x12`) et SC941C (`0x13`).

Composants :
- capture par analyseur logique USB et `sigrok-cli` ;
- décodeur Python du protocole Essensys (codes de trame, CRC-16, écho de réponse, commandes observées) ;
- sonde à trois fils documentée en KiCad et Fritzing.

> ⚠️ L'outil n'émet jamais sur le bus et ne pilote jamais l'armoire. Le branchement se fait hors tension, par une personne habilitée : trois fils (SDA, SCL, 0 V), jamais le +15 V, et aucun pont de masse (hôte sur batterie).

Feature `i2c-ba-sniffer-2026-10-009`, ticket [essensys-hub/essensys-feature-lifecycle#29](https://github.com/essensys-hub/essensys-feature-lifecycle/issues/29). Change OpenSpec : `openspec/changes/i2c-ba-sniffer-2026-10-009/`.

Documentation utilisateur : <https://www.essensys.fr/docs/debug/> (à venir).
