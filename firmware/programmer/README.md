# Programmateur intégré BP / BA — lot de développement

Ce dossier vise le RP2350 nu de la carte FX2/RP2350 du [ticket #10](https://github.com/essensys-hub/essensys-i2c-ba-sniffer/issues/10).
**Les moteurs de protocole sont testés sur l'hôte ; leur accès aux cibles par
USB n'est pas disponible.** Le fichier UF2 livré est un diagnostic qui maintient
les ports inactifs. Aucun BP ou BA réel n'a été programmé avec ce travail.

## Éléments livrés

| Élément | Fonction développée | Limite actuelle |
| --- | --- | --- |
| `icsp.c` | Entrée PIC16F946, identification, lectures, programmation et vérification par callbacks | Adaptation VPP/VDD et qualification BA manquantes ; non exposé sur USB |
| `bdm.c` | Trames ColdFire, arrêt explicite, CSR, lecture flash, reprise explicite | Aucun algorithme d'écriture/effacement BP ; non exposé sur USB |
| `control.c` | Parseur USB borné, diagnostic, STOP, arrêt sur erreur/déconnexion | Aucune commande d'activation ni de programmation |
| `main.c` | UF2 RP2350, sorties inactives, watchdog et diagnostic USB CDC | Aucun GPIO de protocole actionné ; tensions non mesurées |
| `board_contract.h` | Affectations GPIO synchronisées au contrat du schéma | Brochages et niveaux encore à qualifier sur banc |
| `ba_plan.py` côté hôte | Prépare une image dense 8192 mots à partir du HEX strict | Plan hors matériel, sans autorisation de programmation |

Les [notes ICSP](README-icsp.md) et [notes BDM](README-bdm.md) donnent les sources,
séquences, callbacks et limites. Les tests des moteurs injectent des réponses
de cible synthétiques ; ils ne remplacent pas un oscilloscope ou un prototype.

`essensys-pico plan-ba image.hex` prépare un résumé hors matériel. Les trous de
programme seront remplis par `0x3FFF` lors d'une réécriture complète. Un HEX
contenant de l'EEPROM impose un choix explicite `--eeprom preserve` ou `replace` ;
le remplacement exige les 256 octets. Les user IDs ne sont pas modifiés : s'ils
sont présents dans le HEX, la CLI refuse le plan faute de relevé actuel de cible.
L'API Python permet leur comparaison avec un relevé fourni par le futur
orchestrateur. Aucune donnée du firmware ou de l'EEPROM n'est imprimée dans le résumé.

## Deux images firmware différentes

Depuis la racine, utiliser la [procédure de compilation](../README.md) avec le
SDK 2.3.1. CMake produit désormais :

- `build/pico2/essensys_pico2.uf2` : ancien module Pico, capture PIO.
- `build/pico2/essensys_programmer.uf2` : diagnostic de la nouvelle carte,
  capture confiée au FX2 indépendant.

**Ne pas utiliser l'UF2 de capture sur les GPIO de la carte intégrée.** GPIO12/13
ont des rôles différents dans les deux études. Le profil de compilation `pico2`
fournit le démarrage RP2350 pour essais de développement ; il ne certifie pas
la nouvelle carte, sa flash ou ses alimentations.

Les deux moteurs sont compilés pour Arm et testés nativement. Ils ne sont pas
reliés à des callbacks GPIO actifs dans l'UF2 de diagnostic ; aucune option
USB ne transforme `hardware_qualified=false` en autorisation matérielle.

## Diagnostic USB

```sh
pip install -e '.[pico]'
essensys-pico programmer-info --port /dev/ttyACM0
essensys-pico programmer-status --port /dev/ttyACM0
essensys-pico programmer-stop --port /dev/ttyACM0
```

Une commande ASCII terminée par LF ou CRLF, sans pipelining ; une ligne JSON
en réponse, schéma `essensys.programmer.v1`. Le client refuse le schéma de
l'ancien firmware de capture et les réponses tronquées ou incohérentes.

| Commande | Réponse |
| --- | --- |
| `INFO` | `kind=info`, ports BP/BDM et BA/ICSP, `hardware_qualified=false`, `programming_enabled=false` |
| `STATUS` | `kind=state`, `target=none`, sorties commandées inactives, `rails_measured=false` |
| `STOP` | Désactive les enables et relâche les signaux ; `kind=stopped` |
| `SELECT BP`, `SELECT BA` | Refus `board-not-qualified` |
| Toute autre commande | Refus `unsupported-command` |

Une trame contient au plus 63 caractères ; un délai global d'une seconde,
un caractère invalide ou un dépassement impose le repli et le rejet jusqu'au
LF suivant. La déconnexion USB réinitialise le parseur et les sorties.
Le watchdog de deux secondes couvre aussi un blocage du transport. Les états
électriques au reset doivent être garantis par les résistances/étages matériels.
`outputs_commanded_safe` décrit une commande, **pas une mesure** de VPP.

## Alimentation et identité USB de développement

Le diagnostic fonctionne à 48 MHz et son descripteur demande 100 mA, soit une
charge USB2 unitaire. Le SDK standard déclare 250 mA ; un descripteur CDC dédié
évite de reprendre cette déclaration derrière le hub bus-powered. **Le courant
réel, l'appel de courant et le suspend restent à mesurer** ; cette valeur ne
constitue pas une conformité électrique. Le mode auto-alimenté n'est pas déclaré.

VID/PID de développement repris du profil Pico SDK `2e8a:0009`, sans numéro de
série de cible ni interface de reset USB. Une identité de produit autorisée
reste à attribuer avant distribution de la carte ; le pilote FX2 conserve sa
propre interface USB. Source : SDK 2.3.1, `pico_stdio_usb/stdio_usb_descriptors.c`.

## Intégration matérielle restante

1. Qualifier les interfaces BP/BA, le câblage, les mesures de tension et les
   états au boot/reset/défaut ; VPP ne doit jamais rejoindre le BP.
2. Réaliser les callbacks des moteurs sur le matériel qualifié : délais,
   surveillance des rails, annulation USB, exclusion des ports et repli matériel.
3. Ajouter des transferts USB bornés et une sauvegarde persistante liée à la
   cible avant écriture. Une valeur de configuration du HEX ne prouve pas la
   configuration actuellement installée dans le BA.
4. Pour BP, implémenter l'algorithme flash CFM, préserver bootloader,
   configuration et persistance, puis tester la récupération après interruption.
5. Valider les trois variantes BA et le BP sur banc, avant de déclarer la
   programmation ou les fichiers de fabrication prêts.

## Vérifications

`uv run --extra dev pytest -q` couvre le corpus passif existant, les moteurs C,
les défauts USB et l'accord des affectations GPIO entre schéma et firmware.
La compilation Arm et les artefacts ELF/UF2 sont aussi contrôlés en CI.
