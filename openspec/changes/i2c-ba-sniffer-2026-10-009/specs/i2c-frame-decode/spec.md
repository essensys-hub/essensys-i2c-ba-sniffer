## Purpose

Reconstituer et valider, à partir des événements I2C fournis par la capture sigrok, chaque échange BP↔BA du protocole Essensys (identité du BA, code de trame, longueur, CRC-16, écho de réponse), afin de dire précisément où une commande se perd.

## ADDED Requirements

### Requirement: Adresse non acquittée qualifiée comme BA absent

Le décodeur SHALL produire, pour toute phase d'écriture dont l'octet d'adresse reçoit un NACK, un enregistrement « BA absent à l'adresse » portant l'adresse brute, l'identité résolue et l'horodatage, et SHALL compter ces occurrences par adresse.

#### Scenario: NACK sur l'adresse du BA chambres

- **WHEN** la capture contient `START`, l'adresse `0x12` en écriture, puis un NACK et un `STOP`
- **THEN** le décodeur produit un enregistrement « BA 1 (chambres) absent : NACK d'adresse » et incrémente le compteur de NACK de `0x12`

#### Scenario: BA présent distingué

- **WHEN** l'adresse `0x11` est acquittée puis suivie d'octets de données
- **THEN** aucun enregistrement « BA absent » n'est produit pour `0x11`


### Requirement: Reconstruction de la transaction write puis read

Le décodeur SHALL reconstituer une transaction BP↔BA complète à partir de la phase d'écriture
(`START + addr(W)` + N octets) et de la phase de lecture qui la suit après repeated START
(`addr(R)` + 5 octets), et SHALL les présenter comme un unique échange requête/réponse.

#### Scenario: Échange complet présenté comme une unité

- **WHEN** une transaction contient une phase d'écriture puis une phase de lecture séparées par un repeated START vers la même adresse
- **THEN** le décodeur produit un seul enregistrement contenant la requête et la réponse associées

#### Scenario: Écriture sans réponse signalée

- **WHEN** une phase d'écriture est suivie d'un STOP sans phase de lecture
- **THEN** l'enregistrement produit indique une requête sans réponse, sans inventer de réponse par défaut

### Requirement: Identification du boîtier auxiliaire par son adresse

Le décodeur SHALL traduire l'adresse esclave en identité de boîtier selon la dérivation du firmware
maître (`I2C_BUS_ADDRESS_BA = 0x11` + numéro de BA) : `0x11` → BA 0 (pièces de vie), `0x12` → BA 1
(chambres), `0x13` → BA 2 (pièces d'eau). Le décodeur SHALL conserver l'adresse brute dans la sortie en
plus de l'identité résolue.

#### Scenario: Adresse résolue en identité fonctionnelle

- **WHEN** une transaction cible l'adresse `0x12`
- **THEN** l'enregistrement porte à la fois `addr: 0x12` et l'identité BA 1 / chambres

#### Scenario: Adresse hors plage conservée telle quelle

- **WHEN** une transaction cible une adresse hors de `0x11`-`0x13`
- **THEN** l'enregistrement porte l'adresse brute et une identité non résolue, sans être rejeté

### Requirement: Validation de la longueur attendue par code de trame

Le décodeur SHALL vérifier que le nombre d'octets écrits correspond à la longueur attendue pour le code
de trame, telle qu'imposée par le firmware esclave : `1 FORCAGE_SORTIES` → 11 octets, `2 CONF_SORTIES` →
11, `3 TPS_EXTINCTION` → 19, `4 TPS_ACTION` → 11, `5 ACTIONS` → 4. Le décodeur SHALL signaler toute
divergence comme une anomalie protocolaire.

#### Scenario: Longueur conforme validée

- **WHEN** une trame de code `1` comporte 11 octets sur le fil
- **THEN** le décodeur la marque conforme en longueur et poursuit le décodage sémantique

#### Scenario: Longueur non conforme signalée sans interprétation

- **WHEN** une trame de code `3` comporte un nombre d'octets différent de 19
- **THEN** le décodeur émet une anomalie de longueur et n'applique aucune interprétation sémantique des champs

#### Scenario: Code de trame inconnu signalé

- **WHEN** le premier octet écrit ne correspond à aucun des codes `1` à `5`
- **THEN** le décodeur marque la trame comme code inconnu, conserve les octets bruts, et signale que le BA la rejettera

### Requirement: Vérification indépendante du CRC-16 de la requête

Le décodeur SHALL recalculer le CRC-16/MODBUS (initialisation `0xFFFF`, polynôme réfléchi `0xA001`, sans
XOR final), algorithme confirmé dans `crc.c` (`us_CalculerCRCSurTrame`) du firmware BP, sur les octets de
la trame hors CRC, et SHALL le comparer aux deux derniers octets transmis en little-endian. L'ordre des
octets sur le fil SHALL être confirmé sur une capture réelle avant d'être considéré comme acquis.

#### Scenario: CRC valide confirmé

- **WHEN** le CRC recalculé correspond aux deux derniers octets de la trame écrite
- **THEN** l'enregistrement indique un CRC de requête valide

#### Scenario: CRC invalide signalé comme cause probable de rejet

- **WHEN** le CRC recalculé diffère du CRC transmis
- **THEN** l'enregistrement indique un CRC de requête invalide et signale que le BA rejettera la trame, en fournissant la valeur attendue et la valeur reçue

### Requirement: Décodage et vérification de la réponse du BA

Le décodeur SHALL interpréter les 5 octets de réponse comme `[écho du code de trame][CRC de la requête
LO][CRC de la requête HI][CRC-16 de la réponse LO][CRC-16 de la réponse HI]`, SHALL vérifier que l'écho
du code correspond au code émis, SHALL vérifier que le CRC renvoyé correspond au CRC effectivement émis
par le maître, et SHALL recalculer le CRC-16 sur les 3 premiers octets de la réponse.

#### Scenario: Réponse cohérente reconnue comme acquittement applicatif

- **WHEN** l'écho du code correspond, le CRC renvoyé égale le CRC émis, et le CRC de la réponse est valide
- **THEN** l'enregistrement indique que le BA a reçu et validé la trame

#### Scenario: Écho de CRC divergent signalé

- **WHEN** le CRC renvoyé par le BA diffère du CRC émis par le maître
- **THEN** l'enregistrement signale un rejet côté BA et explicite la divergence, sans conclure à un succès de commande

#### Scenario: Réponse d'acquittement distinguée d'un état de sortie

- **WHEN** une réponse cohérente est décodée
- **THEN** la sortie qualifie explicitement cet acquittement comme « trame reçue et validée CRC », et jamais comme « sortie physiquement commutée »

### Requirement: Détection des répétitions de trame

Le décodeur SHALL détecter la réémission d'une trame identique (même BA, même code, même charge utile)
dans une fenêtre temporelle courte, et SHALL la présenter comme une répétition, cohérente avec le
mécanisme de répétition sur erreur du firmware maître.

#### Scenario: Répétition sur erreur mise en évidence

- **WHEN** la même trame est réémise vers le même BA après une réponse en erreur
- **THEN** la sortie indique une répétition et son rang, plutôt que de présenter plusieurs commandes utilisateur distinctes

#### Scenario: Abandon après répétitions signalé

- **WHEN** une série de répétitions d'une même trame se termine sans réponse valide et sans nouvelle tentative
- **THEN** la sortie signale une commande probablement abandonnée par le maître, jamais reçue par le BA

### Requirement: Décodage rejouable sur capture enregistrée

Le décodeur SHALL produire exactement les mêmes résultats en traitant une capture enregistrée qu'en
traitant le même trafic en temps réel.

#### Scenario: Rejeu identique au temps réel

- **WHEN** une capture est enregistrée pendant une session temps réel puis rejouée hors ligne par le décodeur
- **THEN** les enregistrements décodés sont identiques à ceux produits en temps réel, hors horodatage d'hôte
