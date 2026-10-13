## Purpose

Publier sur `https://www.essensys.fr/docs/debug/` une documentation complète, compréhensible par un mainteneur non spécialiste, pour fabriquer et utiliser l'espion I2C en toute sécurité, puis interpréter ses captures.

## ADDED Requirements

### Requirement: Section Debug publiée

essensys-doc SHALL comporter une section « Debug » dans la navigation, accessible sous `docs/debug/`. Elle SHALL comporter au moins :
- une page d'index ;
- une page « Espion I2C passif ».

La page « Espion I2C passif » SHALL couvrir : objectif, matériel et nomenclature, sécurité, fabrication de la sonde, installation de sigrok et du décodeur, mode opératoire, lecture des captures, limites. La section SHALL être construite avec `mkdocs build --strict` sans avertissement, puis publiée par le rôle `docs_site`.

#### Scenario: Page accessible en production

- **WHEN** un visiteur ouvre `https://www.essensys.fr/docs/debug/`
- **THEN** la page d'index s'affiche et renvoie vers la page de l'espion I2C

### Requirement: Schémas intégrés

La documentation SHALL intégrer :
- un schéma Archify de la chaîne de debug (bus, sonde, analyseur, hôte, décodeur, corrélation avec les journaux CM5) ;
- l'export Fritzing du câblage ;
- l'export du schéma KiCad de la sonde.

Elle SHALL renvoyer vers les sources de ces schémas dans le dépôt.

#### Scenario: Les trois schémas présents

- **WHEN** on parcourt la page « Espion I2C passif »
- **THEN** on y trouve le schéma Archify, le câblage Fritzing et le schéma KiCad, chacun légendé et relié à sa source

### Requirement: Règles de sécurité explicites

La documentation SHALL imposer, dans un encadré placé avant toute étape de branchement :
- branchement et débranchement hors tension, par une personne habilitée ;
- trois fils seulement, jamais le +15 V ;
- aucun pont de masse ;
- outil strictement passif ;
- commandes d'essai déclenchées par l'exploitant depuis l'interface habituelle.

#### Scenario: Encadré de sécurité avant le câblage

- **WHEN** on lit la page dans l'ordre
- **THEN** l'encadré de sécurité apparaît avant la première instruction de branchement

### Requirement: Guide d'interprétation

La documentation SHALL fournir un tableau qui associe chaque observation à son diagnostic et à l'action suivante :
- échange normal ;
- NACK d'adresse ;
- écho CRC faux ;
- ligne bloquée ;
- aucune trame après une commande ;
- répétitions puis abandon.

Elle SHALL rappeler qu'un acquittement backend ou une trame validée ne prouve pas la commutation physique, et que le BP ne fait qu'un seul essai par nouvel ordre vers un BA déjà en défaut.

#### Scenario: Diagnostic d'un BA muet

- **WHEN** un mainteneur observe des NACK sur `0x12` après une commande « chevet petite chambre 3 »
- **THEN** le tableau l'oriente vers « BA chambres absent » et vers la procédure de remise en service après surtension

### Requirement: Données anonymisées

Les pages, captures d'exemple et schémas publiés SHALL ne contenir aucune adresse IP du LAN de l'exploitant, adresse MAC, numéro de série, lieu ni nom d'installateur.

#### Scenario: Contrôle avant publication

- **WHEN** on recherche des adresses du LAN privé ou des adresses MAC dans la section `docs/debug/` et les captures publiées
- **THEN** aucune occurrence n'est trouvée, hors plan produit `10.0.1.0/24` et plage d'exemple RFC 5737
