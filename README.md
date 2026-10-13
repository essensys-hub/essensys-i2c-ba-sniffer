# essensys-i2c-ba-sniffer

Espion I2C **strictement passif** du bus interne de l'armoire Essensys : boîtier principal SC944D (maître, `0x10`) ↔ boîtiers auxiliaires SC940D (`0x11`, pièces de vie), SC942C (`0x12`, chambres) et SC941C (`0x13`, pièces d'eau).

- Capture par analyseur logique USB (pilote sigrok `fx2lafw`) et `sigrok-cli`, sur un Raspberry Pi ou un portable **sur batterie**.
- Décodeur Python du protocole Essensys :
  - transactions, identité des BA, longueur par code de trame, CRC-16/MODBUS, écho de réponse ;
  - répétitions et abandons du maître, lignes bloquées ;
  - commandes observées (lampes, variateurs, volets, drapeaux).
- Corrélation avec les journaux du backend CM5 (`Sending Actions` / `Action acknowledged`).
- Sonde à trois fils documentée en KiCad et Fritzing (`hardware/`, à venir).

> ⚠️ **L'outil n'émet jamais sur le bus et ne pilote jamais l'armoire.**
> - Branchement et débranchement **hors tension**, par une personne habilitée.
> - Trois fils seulement : SDA, SCL et 0 V, jamais le +15 V.
> - **Aucun pont de masse** : hôte sur batterie, en Wi-Fi seulement, ou isolateur USB.
> - Les commandes d'essai sont déclenchées par l'exploitant depuis l'interface habituelle.

## Installation

```bash
sudo apt install sigrok-cli sigrok-firmware-fx2lafw   # Raspberry Pi OS / Debian
pip install git+https://github.com/essensys-hub/essensys-i2c-ba-sniffer
```

## Utilisation

```bash
# Capture en direct : D0 = SCL, D1 = SDA, 1 MHz minimum (20 fois le bus à 50 kHz)
essensys-i2c-sniff live --raw-out captures/local/session.bin

# Rejeu d'une capture (.sr de PulseView, .bin ou .bin.gz)
essensys-i2c-sniff replay captures/local/session.bin --format ndjson > session.ndjson

# Corrélation avec les journaux du backend exportés depuis la gateway
essensys-i2c-sniff correlate --capture session.ndjson --backend-log backend.log
```

Exemple sur le cas réel du 2026-10-13 (corpus `cas_installation_2026_10`, signal synthétique) :

```text
       1.005 ms  0x11 pièces de vie — FORCAGE_SORTIES — lampe 0 → ON (commande observée) — trame reçue et validée CRC par le BA
     104.295 ms  0x12 chambres — NACK d'adresse — BA absent (n° 1)
     204.505 ms  0x13 pièces d'eau — NACK d'adresse — BA absent (n° 1)
```

« Trame reçue et validée CRC » ne prouve pas que la sortie a commuté : le protocole ne renvoie jamais l'état physique.

## Développement

```bash
pip install -e '.[dev]' && pytest -q      # tests unitaires et NR-i2c-ba-sniffer-1 à -6, sans matériel
python tools/make_corpus.py               # régénère le corpus (sigrok-cli requis), à relire
```

Le corpus `captures/corpus/` contient des signaux synthétiques annotés par le décodeur I2C de sigrok, qui sert d'oracle indépendant.

## Références

- Feature `i2c-ba-sniffer-2026-10-009`, ticket [essensys-hub/essensys-feature-lifecycle#29](https://github.com/essensys-hub/essensys-feature-lifecycle/issues/29), change `openspec/changes/i2c-ba-sniffer-2026-10-009/`.
- Documentation utilisateur : <https://www.essensys.fr/docs/debug/> (à venir).
- Phase 2 (Raspberry Pi Pico) : change `essensys-i2c-ba-sniffer-2026-07-038` (essensys-memory). Version permanente : module ESP32 de la carte N2 (`n2-esp32-spy-alarm-2026-10-008`).
