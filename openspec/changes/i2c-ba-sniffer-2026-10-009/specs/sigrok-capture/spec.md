## Purpose

Acquérir le trafic du bus I2C BP↔BA de manière strictement passive, avec un analyseur logique USB du commerce et sigrok. Le décodeur doit recevoir des événements I2C fiables, en direct ou en rejeu, sans jamais perturber le bus.

## ADDED Requirements

### Requirement: Aucune émission sur le bus

L'outil SHALL ne jamais piloter SDA ni SCL. L'acquisition SHALL se faire uniquement par des entrées d'analyseur logique. Aucune commande de l'outil SHALL configurer un contrôleur I2C, ajouter une pull-up ou écrire sur le bus. Aucune commande SHALL non plus déclencher un ordre domotique sur l'installation.

#### Scenario: Compteurs d'erreurs du BP inchangés

- **WHEN** la sonde est raccordée puis retirée pendant au moins 10 minutes de fonctionnement sur banc
- **THEN** l'index 12 et les compteurs d'erreurs I2C du BP restent identiques à ceux mesurés sans sonde

#### Scenario: Aucune commande d'écriture exposée

- **WHEN** on liste les commandes et options de l'outil
- **THEN** aucune ne permet d'émettre une trame I2C ni d'injecter une action dans le backend

### Requirement: Acquisition sigrok en direct et en rejeu

L'outil SHALL accepter comme entrée :
- le flux du décodeur de protocole I2C de `sigrok-cli`, en direct ;
- une session sigrok enregistrée (`.sr`), rejouée hors ligne.

L'acquisition SHALL échantillonner à au moins 1 MHz, soit 20 fois le débit du bus à 50 kHz. Elle SHALL refuser une fréquence inférieure.

#### Scenario: Capture en direct

- **WHEN** l'opérateur lance la capture avec un analyseur `fx2lafw` branché, sur les voies SCL et SDA déclarées
- **THEN** les événements START, adresse, données, ACK/NACK, repeated START et STOP sont transmis au décodeur au fil de l'eau

#### Scenario: Fréquence d'échantillonnage insuffisante refusée

- **WHEN** l'opérateur demande une fréquence d'échantillonnage inférieure à 1 MHz
- **THEN** l'outil refuse de démarrer et indique la fréquence minimale

#### Scenario: Session enregistrée rejouée

- **WHEN** l'opérateur fournit un fichier `.sr` capturé auparavant
- **THEN** le décodeur produit les mêmes enregistrements qu'en direct, hors horodatage d'hôte

### Requirement: Détection des défauts logiques du bus

L'outil SHALL signaler :
- une ligne SDA ou SCL maintenue au niveau bas pendant plus de 10 ms ;
- une trame interrompue sans STOP ;
- un débordement d'acquisition.

Chaque défaut SHALL porter son horodatage et sa durée.

#### Scenario: Ligne bloquée au niveau bas

- **WHEN** SDA reste au niveau bas plus de 10 ms en dehors d'une transaction
- **THEN** l'outil émet un événement « SDA bloquée basse » avec le début et la durée

#### Scenario: Débordement signalé, jamais masqué

- **WHEN** l'analyseur perd des échantillons
- **THEN** l'outil émet un événement de débordement, et le décodage de la période concernée est marqué incomplet
