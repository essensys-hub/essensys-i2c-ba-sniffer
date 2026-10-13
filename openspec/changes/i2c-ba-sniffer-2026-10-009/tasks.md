## 1. Amorçage du dépôt (#1)

- [x] 1.1 Créer l'arborescence `decoder/essensys_i2c_sniffer/`, `tests/`, `captures/`, `hardware/kicad/`, `hardware/fritzing/`, `docs/`, et un `pyproject.toml` (Python ≥ 3.11, aucune dépendance d'exécution, CLI `essensys-i2c-sniff`). Vérifier : `pip install -e .` puis `essensys-i2c-sniff --help` répond.
- [x] 1.2 Ajouter la CI GitHub Actions avec `pytest`, `kicad-cli sch erc` dans une image KiCad 9, et un contrôle d'anonymisation (`git grep` des IP du LAN privé et des MAC). Vérifier : la CI passe sur la branche.
- [x] 1.3 Rédiger le README : objectif, avertissement « strictement passif », renvoi vers `docs/debug/`. Vérifier : relu, sans donnée privée.

## 2. Décodeur : transactions et trames (#2)

- [x] 2.1 Parser la sortie `sigrok-cli -P i2c -A i2c --protocol-decoder-samplenum`, en direct par tube et en rejeu `.sr`, en événements typés (START, Sr, STOP, adresse W/R, données, ACK/NACK). Vérifier par des tests unitaires sur des extraits annotés, lignes tronquées comprises.
- [x] 2.2 Reconstruire les transactions écriture → repeated START → lecture de 5 octets → STOP, avec le cas « écriture sans réponse ». Vérifier par des tests unitaires.
- [x] 2.3 Qualifier un NACK d'adresse comme « BA absent », avec un compteur par adresse, et résoudre l'identité 0x11 / 0x12 / 0x13 en gardant l'adresse brute. Vérifier par un test (NR-i2c-ba-sniffer-2).
- [x] 2.4 Valider la longueur selon le code de trame (11 / 11 / 19 / 11 / 4) et signaler les codes inconnus. Vérifier par des tests unitaires.
- [x] 2.5 Recalculer le CRC-16/MODBUS de la requête et décoder la réponse de 5 octets (écho du code, écho du CRC, CRC de la réponse). Vérifier par des tests sur des vecteurs calculés avec l'algorithme de `crc.c` (NR-i2c-ba-sniffer-3).
- [x] 2.6 Détecter les répétitions d'une même trame et l'abandon après épuisement. Vérifier par un test sur une séquence synthétique (NR-i2c-ba-sniffer-4).

## 3. Décodeur : sémantique domotique (#3)

- [x] 3.1 Décoder `FORCAGE_SORTIES` en commandes observées (lampes 0-15, variateurs, volets sens 1 / sens 2) avec les priorités du firmware BA. Vérifier par des tests unitaires, conflits compris.
- [x] 3.2 Appliquer les profils de sorties par adresse (PDV 5/3/6, CHB 7/4/5, PDE 13/1/4, surchargeables) et signaler les bits hors plage. Vérifier par des tests unitaires.
- [x] 3.3 Décoder `CONF_SORTIES`, `TPS_EXTINCTION`, `TPS_ACTION` et `ACTIONS`, en restituant en brut les octets de bourrage et les bits réservés. Vérifier par des tests unitaires.
- [x] 3.4 Reconstruire un état commandé cumulé, marqué « inféré » (les sorties jamais vues sont « inconnues »). Vérifier par un test.

## 4. Outillage : CLI, NDJSON, corrélation, corpus (#4)

- [x] 4.1 Implémenter la CLI : capture en direct (lance `sigrok-cli` avec `fx2lafw`, voies D0 = SCL et D1 = SDA, au moins 1 MHz, refus en dessous), rejeu `.sr`, sorties texte et NDJSON versionnée (`schema`). Vérifier qu'une fréquence de 500 kHz est refusée et que la sortie NDJSON est valide.
- [x] 4.2 Détecter les lignes bloquées plus de 10 ms (analyse du flux brut, voir design D2) et les débordements d'acquisition, en marquant la période concernée comme incomplète. Vérifier par un test sur une capture synthétique (NR-i2c-ba-sniffer-5).
- [x] 4.3 Implémenter la corrélation avec un fichier de journaux backend (`Sending Actions` / `Action acknowledged`) : recalage d'horloge et rapport « acquittée mais non reçue par le BA ». Vérifier par un test sur un journal anonymisé et une capture associée.
- [x] 4.4 Constituer le corpus de référence : 5 codes de trame, NACK d'adresse, CRC faux, répétitions puis abandon, ligne bloquée, chacun avec sa sortie NDJSON attendue. Vérifier : le rejeu est strictement identique (NR-i2c-ba-sniffer-6).
- [x] 4.5 Garantir l'absence de toute commande d'émission ou d'injection. Vérifier par un test qui inspecte la CLI et le paquet (NR-i2c-ba-sniffer-1).

## 5. Sonde matérielle : KiCad et Fritzing (#5)

- [ ] 5.1 Relever la référence du connecteur J1/J2 des BA dans les BOM SC940D/SC941C/SC942C et la consigner dans `hardware/README.md`. Vérifier par recoupement avec une photo de la carte, floutée si elle est publiée.
- [x] 5.2 Dessiner le schéma KiCad de la sonde : connecteur sans broche 4, 1 kΩ série, protection ESD de faible capacité, `74LVC2G17` alimenté en 3,3 V, sortie vers l'analyseur, aucune pull-up. Vérifier : ERC sans erreur en CI.
- [x] 5.3 Décider entre PCB et plaque à pastilles. Si PCB : router et vérifier un DRC sans erreur, puis exporter Gerber, BOM et PDF dans `hardware/kicad/export/`.
- [x] 5.4 Réaliser le câblage Fritzing (`.fzz`) BA → sonde → analyseur FX2 → Raspberry Pi sur batterie, avec ses exports SVG et PNG. Vérifier : le fichier s'ouvre et les exports sont versionnés.
- [ ] 5.5 Contrôler la sonde fabriquée à l'ohmmètre (aucune continuité vers la position de broche 4) et l'entrée tolérant 5,5 V. Vérifier par une fiche de mesures dans `hardware/`.

## 6. Validation sur banc et capture passive réelle (#6)

- [ ] 6.1 Sur banc (jamais sur une armoire de production pour la mise au point), mesurer les niveaux et les temps de montée avec et sans sonde. Vérifier qu'ils restent dans les tolérances du change i2c-surge-protection-2026-10-007, et que les compteurs d'erreurs du BP sont inchangés pendant 10 minutes.
- [ ] 6.2 Relire les captures du banc dans PulseView et comparer trame à trame avec le décodeur. Vérifier : aucun écart, ou chaque écart corrigé.
- [ ] 6.3 Confirmer sur des trames réelles l'ordre des octets du CRC et l'ordre des bits de `ACTIONS`, puis figer les sorties attendues. Vérifier : tests du corpus mis à jour et verts.
- [ ] 6.4 Faire une capture passive sur l'installation touchée : branchement hors tension par une personne habilitée, hôte sur batterie, commandes déclenchées par l'exploitant (une vers chaque BA). Vérifier : l'état réel de 0x11, 0x12 et 0x13 est établi (ACK ou NACK, CRC), et une synthèse anonymisée est ajoutée à essensys-hub/essensys-board-SC944D#2 après accord.
- [ ] 6.5 Exécuter `/checkup` sur la feature (build, lint, unitaires, NR, gates). Vérifier : rapport vert publié sur essensys-hub/essensys-feature-lifecycle#29.

## 7. Documentation publique `docs/debug/` (essensys-hub/essensys-doc#9)

- [x] 7.1 Créer la section Debug dans essensys-doc (`docs/debug/index.md`, entrée de navigation mkdocs). Vérifier : `mkdocs build --strict` passe.
- [x] 7.2 Rédiger `docs/debug/espion-i2c.md` avec ces sections :
  - objectif ;
  - nomenclature ;
  - encadré de sécurité placé avant tout branchement ;
  - fabrication de la sonde ;
  - installation de sigrok et du décodeur ;
  - mode opératoire, avec un seul essai par clic sur un BA en défaut ;
  - tableau d'interprétation ;
  - limites ;
  - liens vers `install/ajout-bp.md` et `install/remise-en-service-surtension.md`.

  Vérifier : relecture et build strict.
- [x] 7.3 Produire le schéma Archify de la chaîne de debug (source JSON versionnée, rendu en iframe) et intégrer les exports Fritzing et KiCad. Vérifier : les trois schémas s'affichent dans le site construit.
- [x] 7.4 Contrôler l'anonymisation de la section (IP, MAC, n° de série, lieu). Vérifier : la recherche ne trouve rien.
- [ ] 7.5 Après relecture et fusion, publier avec le rôle Ansible `docs_site`. Vérifier : `https://www.essensys.fr/docs/debug/` répond.

## 8. Mémoire projet (essensys-hub/essensys-memory#16)

- [x] 8.1 Ajouter au wiki essensys-memory une page sur l'outil (entité du dépôt et concept « espion I2C passif »), et noter que le change `essensys-i2c-ba-sniffer-2026-07-038` devient la phase 2 (Pico). Vérifier : wikilinks résolus et index mis à jour.
- [ ] 8.2 Après la capture réelle (6.4), consigner la synthèse anonymisée dans la page de l'incident foudre. Vérifier : relecture, aucune donnée privée.
