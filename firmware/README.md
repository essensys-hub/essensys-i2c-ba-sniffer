# Pico 2 — acquisition huit voies

La nouvelle carte possède maintenant un [lot de développement du programmateur
BP/BA](programmer/README.md), avec moteurs ICSP/BDM testés sur l'hôte et un UF2 de
diagnostic distinct. La suite de cette page décrit l'ancienne capture sur module.

Premier lot du [ticket #10](https://github.com/essensys-hub/essensys-i2c-ba-sniffer/issues/10).
Ce firmware de capture PIO correspond à l'étude initiale sur module Pico 2.
La [nouvelle architecture intégrée RP2350 + FX2](../hardware/pico2/ADR-001-carte-integree.md)
confie l'acquisition principale au FX2 ; ce prototype ne programme pas les BA
et n'est pas le firmware final de cette nouvelle carte.
**Compilé, testé sur l'hôte, non essayé sur Pico physique. La programmation des
BA n'est pas disponible.** La conception ICSP dépend de la qualification décrite
dans [le dossier matériel](../hardware/pico2/README.md).

## Architecture et limites

Une machine PIO lit GPIO0..7 ; DMA dépose les données dans une RAM de 256 Kio.
Le transfert USB commence après l'acquisition. Il n'y a ni flux continu, ni
déclencheur, ni tampon circulaire. La première capture commence à réception de
la commande : les événements antérieurs ne sont pas conservés.

Un échantillon vaut un octet : bit 0 = CH1/SCL, bit 1 = CH2/SDA, puis CH3..8.
Le programme PIO exécute deux cycles par échantillon (IN + JMP), puis se bloque
sur une interruption après le nombre exact demandé. Le pilote refuse un délai
dépassé ou un FIFO RX ayant bloqué pendant la capture. Le CRC32 détecte une
altération des octets après acquisition ; il ne valide pas les niveaux électriques.

- Horloge système : 120 MHz ; diviseur entier `120000000 / (2 × fréquence)`.
- Fréquences acceptées : 1 kHz..10 MHz **si ce diviseur est entier** (1, 2, 5 et
  10 MHz notamment). Refus des fréquences inexactes, sans arrondi caché.
- Taille : 4..262144 échantillons, multiple de 4 ; à 1 MHz, au plus 262,144 ms.
- Le décodeur I2C impose au moins 1 MHz pour le bus 50 kHz.
- 10 MS/s est une limite logicielle calculée ; ni la cadence réelle, ni la bande
  passante avec SP0502, résistances et nappe 1 m ne sont qualifiées. Aucune
  équivalence « 24 MHz » avec le FX2 de référence n'est annoncée.
- GPIO0..7 : entrées sans pulls. GPIO12/13 réservés pour de futurs enables VPP,
  actuellement maintenus à zéro. Aucun autre GPIO n'est utilisé par ce firmware.
- Aucun ordre d'émission I2C, d'effacement ou de programmation PIC.
- Watchdog de 2 s entretenu pendant l'acquisition et les transferts. Après une
  déconnexion ou une trame incomplète, fermer le port et redémarrer le Pico
  avant une nouvelle session ; aucune resynchronisation à chaud n'est garantie.

## Compilation

Outils libres : CMake, Ninja, GCC Arm bare-metal et SDK Raspberry Pi **2.3.1**, commit
`079c6f39023649b154152db30f1d781e884879bc`. Le SDK utilise son picotool 2.3.1
pour produire l'UF2. La CI conserve les fichiers ELF et UF2.

Depuis la racine du dépôt, avec GCC `arm-none-eabi-gcc` dans le PATH :

```sh
git clone https://github.com/raspberrypi/pico-sdk.git ../pico-sdk
git -C ../pico-sdk checkout 079c6f39023649b154152db30f1d781e884879bc
git -C ../pico-sdk submodule update --init lib/tinyusb
PICO_SDK_PATH="$PWD/../pico-sdk" cmake -S firmware -B build/pico2 -G Ninja -DPICO_BOARD=pico2
cmake --build build/pico2
```

Sortie : `build/pico2/essensys_pico2.uf2`. Sur macOS avec une toolchain extraite,
ajouter `-DPICO_TOOLCHAIN_PATH=/chemin/toolchain` à CMake. La première compilation
locale a utilisé GCC 15.3.rel2, SDK 2.3.1 et KiCad 10.0.7 pour le schéma.
Flasher uniquement un Pico 2 de banc par son mode BOOTSEL, déconnecté des BA.

## Outil hôte

```sh
pip install -e '.[pico]'
essensys-pico inspect-hex '/chemin/ba.hex'    # hors matériel, aucun port ouvert
essensys-pico info --port /dev/ttyACM0
essensys-pico capture --port /dev/ttyACM0 --samplerate 1000000 --samples 262144 --out session.bin
essensys-i2c-sniff replay session.bin --format ndjson
```

Adapter le port sur macOS (`/dev/cu.usbmodem…`). La commande `capture` crée un
nouveau `.bin` et son `.bin.json` après validation du nombre d'octets et du CRC.
Elle refuse d'écraser une capture. La date du premier échantillon n'est pas
mesurée : pour une corrélation temporelle, fournir un recalage externe.
Les six autres voies restent dans le brut ; le décodeur Essensys n'interprète
que SCL/SDA. Pour les visualiser, importer le brut dans PulseView, huit voies,
un octet par échantillon et fréquence des métadonnées.

## Protocole USB CDC v1

Une commande ASCII terminée par LF, sans pipelining. Baud CDC nominal 115200
(USB natif). Commandes autorisées :

| Commande | Réponse |
| --- | --- |
| `INFO` | Une ligne JSON de capacités ; `mode=capture-only`, `icsp_enabled=false` |
| `CAPTURE <fréquence> <échantillons>` | JSON ci-dessous, puis exactement N octets binaires |

```json
{"schema":"essensys.pico.v1","status":"ok","kind":"capture","channels":8,"samplerate":1000000,"samples":4,"crc32":3057449933}
```

Exemple pour les octets `01 02 03 04`. CRC32 IEEE réfléchi : polynôme
`0xEDB88320`, initialisation/final XOR `0xffffffff`. Les octets CR/LF dans le
payload sont des données, sans conversion. Un échec retourne une seule ligne
JSON `status=error` et un code `error`, sans payload. L'hôte borne l'en-tête à
512 octets et refuse version, taille, fréquence ou CRC incohérents.

## Vérifications et prochaine qualification

`uv run --extra dev pytest -q` vérifie les limites C, le parseur de commandes,
le CRC, l'Intel HEX, le transport fragmenté/corrompu/tronqué et le rejeu d'une
capture simulée contenant les huit voies dans le décodeur et sigrok existants.
Ces tests ne simulent ni l'électronique ni les périphériques PIO/DMA.

Sur banc avant utilisation : niveaux 0/1 et séquences distinctes sur huit voies,
ordre des bits, fréquence/durée, début/fin de fenêtre, répétitions de captures,
déconnexion USB/watchdog, nappe 1 m et comparaison simultanée avec le FX2.
Consigner les mesures avec les versions matérielles/firmware. Les tâches
OpenSpec physiques restent décochées jusqu'à ce rapport.
