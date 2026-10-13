## Purpose

Mettre les résultats du décodage à disposition de l'exploitant et des tests : affichage lisible, NDJSON pour le rejeu et les diff, corrélation avec les journaux du backend CM5, corpus de captures de référence.

## ADDED Requirements

### Requirement: Sorties lisible et NDJSON

L'outil SHALL proposer :
- une sortie texte lisible, une ligne par échange ;
- une sortie NDJSON, un objet JSON par enregistrement.

Le format NDJSON SHALL être versionné par un champ `schema`. Chaque enregistrement NDJSON SHALL porter l'horodatage, l'adresse brute, l'identité du BA, l'état d'acquittement, les anomalies et les commandes observées.

#### Scenario: Sortie lisible

- **WHEN** l'opérateur lance l'outil sans option de format
- **THEN** chaque échange est affiché sur une ligne, par exemple « 0x12 chambres — NACK d'adresse » ou « 0x11 pièces de vie — FORCAGE_SORTIES — lampe 0 → ON — trame validée CRC »

#### Scenario: NDJSON exploitable par un script

- **WHEN** l'opérateur demande la sortie NDJSON
- **THEN** chaque ligne est un objet JSON valide qui porte le champ `schema`

### Requirement: Corrélation avec les journaux du backend CM5

L'outil SHALL rapprocher, par fenêtre temporelle configurable, les actions vues dans les journaux du backend (`Sending Actions` avec GUID et paramètres k/v, puis `Action acknowledged`) et les trames I2C observées. Il SHALL signaler les actions acquittées côté backend qui n'ont été suivies d'aucune trame valide vers le BA attendu.

#### Scenario: Action acquittée mais perdue sur le bus

- **WHEN** le journal backend contient une action `613 = 64` acquittée, et la capture ne contient vers `0x12` que des NACK d'adresse dans la fenêtre
- **THEN** l'outil rapporte « action <GUID> acquittée par le BP, non reçue par le BA chambres (NACK) »

#### Scenario: Action correctement transmise

- **WHEN** une action vers une lampe des pièces de vie est suivie d'une trame `FORCAGE_SORTIES` validée vers `0x11`
- **THEN** l'outil rapporte l'action comme transmise au BA, avec le rappel qu'une trame validée ne prouve pas la commutation physique

### Requirement: Corpus de captures de référence

Le dépôt SHALL contenir un corpus versionné de captures, anonymisé. Il SHALL couvrir :
- les cinq codes de trame ;
- un NACK d'adresse ;
- un CRC faux ;
- une répétition suivie d'un abandon ;
- une ligne bloquée.

Chaque capture SHALL être accompagnée de sa sortie NDJSON attendue. Les tests SHALL rejouer le corpus sans matériel ni armoire.

#### Scenario: Non-régression sur le corpus

- **WHEN** la suite de tests est exécutée en CI
- **THEN** le décodage de chaque capture du corpus est strictement identique à la sortie attendue versionnée
