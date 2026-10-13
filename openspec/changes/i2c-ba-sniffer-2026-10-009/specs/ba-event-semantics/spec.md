## Purpose

Traduire les trames décodées en commandes domotiques lisibles (lampes, variateurs, volets, drapeaux globaux) par type de boîtier auxiliaire, sans jamais affirmer qu'une sortie a physiquement commuté.

## ADDED Requirements

### Requirement: Décodage sémantique du forçage des sorties

Le décodeur SHALL traduire une trame `FORCAGE_SORTIES` (code `1`) en événements par sortie, selon le
découpage appliqué par le firmware esclave :

| Octet (hors code) | Rôle |
|---|---|
| 1 | lampes à éteindre, bits 0-7 |
| 2 | lampes à allumer, bits 0-7 |
| 3 | lampes à éteindre, bits 8-15 |
| 4 | lampes à allumer, bits 8-15 |
| 5 | variateurs à éteindre |
| 6 | variateurs à allumer |
| 7 | volets — sens 1 (montée / ouverture) |
| 8 | volets — sens 2 (descente / fermeture) |

Le décodeur SHALL n'émettre d'événement que pour les bits effectivement positionnés, et SHALL nommer
chaque événement par le BA, le type de sortie et l'index de sortie.

#### Scenario: Allumage d'une lampe décodé

- **WHEN** une trame `FORCAGE_SORTIES` vers `0x12` porte le bit 4 de l'octet « lampes à allumer, bits 0-7 »
- **THEN** le décodeur émet un événement « BA 1 (chambres) — lampe 4 → ON »

#### Scenario: Montée d'un volet décodée

- **WHEN** le bit 2 de l'octet « volets sens 1 » est positionné
- **THEN** le décodeur émet un événement « volet 2 → montée/ouverture », et non un événement de lampe

#### Scenario: Aucun bit positionné

- **WHEN** une trame `FORCAGE_SORTIES` valide ne porte aucun bit de commande
- **THEN** le décodeur émet la trame sans aucun événement de sortie, et signale explicitement qu'aucune sortie n'est commandée

### Requirement: Application des règles de priorité du firmware esclave

Le décodeur SHALL reproduire les priorités appliquées par le firmware BA lorsqu'un même équipement est
commandé simultanément dans les deux sens : **extinction prioritaire sur allumage** pour les lampes et
les variateurs, **montée/ouverture prioritaire sur descente/fermeture** pour les volets.

#### Scenario: Lampe commandée ON et OFF simultanément

- **WHEN** le même index de lampe est positionné à la fois dans le masque « allumer » et dans le masque « éteindre »
- **THEN** le décodeur émet l'événement effectif « OFF » et signale le conflit de commande dans l'enregistrement

#### Scenario: Volet commandé dans les deux sens

- **WHEN** le même index de volet est positionné dans les masques sens 1 et sens 2
- **THEN** le décodeur émet l'événement effectif « montée/ouverture » et signale le conflit

### Requirement: Décodage des actions globales

Le décodeur SHALL traduire l'octet utile de la trame `ACTIONS` (code `5`) en drapeaux nommés : bit 0
« mode secouru / sauvegarde d'état », bit 1 « blocage des volets », bit 2 « forçage de l'allumage
général ». Le décodeur SHALL signaler les bits inutilisés lorsqu'ils sont positionnés.

#### Scenario: Blocage des volets décodé

- **WHEN** une trame `ACTIONS` porte le bit de blocage des volets
- **THEN** le décodeur émet un événement « blocage volets → actif » pour le BA concerné

#### Scenario: Transition de drapeau mise en évidence

- **WHEN** deux trames `ACTIONS` successives vers le même BA diffèrent d'un seul drapeau
- **THEN** le décodeur met en évidence la transition de ce drapeau plutôt que de réafficher l'état complet sans distinction

#### Scenario: Bit réservé positionné signalé

- **WHEN** un bit documenté comme non utilisé est positionné dans la trame `ACTIONS`
- **THEN** le décodeur émet une anomalie de champ réservé, avec la valeur brute de l'octet

### Requirement: Décodage des trames de configuration

Le décodeur SHALL décoder les trames de configuration en champs nommés : `CONF_SORTIES` (code `2`) →
mode de chaque variateur sur 3 bits (`& 0x07`) ; `TPS_EXTINCTION` (code `3`) → temps maximal d'allumage
par relais lampe, en minutes ; `TPS_ACTION` (code `4`) → temps maximal de commande par volet, en
secondes. Le décodeur SHALL indiquer que ces trames provoquent une écriture EEPROM côté BA lorsque la
valeur change.

#### Scenario: Temps d'extinction décodé en minutes

- **WHEN** une trame `TPS_EXTINCTION` est capturée
- **THEN** chaque octet utile est présenté comme le temps maximal d'allumage du relais correspondant, avec la valeur `0` explicitée comme « pas d'extinction automatique »

#### Scenario: Octets de bourrage non interprétés

- **WHEN** une trame porte plus d'octets utiles que le nombre de sorties réellement exploitées par le BA
- **THEN** le décodeur décode les champs exploités et restitue les octets excédentaires en brut, sans leur inventer de signification

### Requirement: Profils de sorties par type de boîtier

Le décodeur SHALL appliquer, par adresse, le profil de sorties relevé dans `hard.c` des firmwares BA v1.7 :
`0x11` pièces de vie (SC940D) → 5 relais lampes, 3 variateurs, 6 volets ; `0x12` chambres (SC942C) →
7 relais lampes, 4 variateurs, 5 volets ; `0x13` pièces d'eau (SC941C) → 13 relais lampes, 1 variateur,
4 volets. Le décodeur SHALL permettre de surcharger ces profils par configuration, et SHALL signaler tout
bit positionné au-delà du nombre de sorties du profil.

#### Scenario: Bit hors plage signalé

- **WHEN** une trame vers `0x12` positionne le bit de lampe 9 alors que le profil chambres compte 7 relais lampes
- **THEN** le décodeur émet une anomalie « index de sortie hors plage » plutôt qu'un événement de sortie inexistante

#### Scenario: Profil propre à chaque boîtier

- **WHEN** des trames vers `0x11` et `0x13` sont décodées dans la même capture
- **THEN** chaque trame est interprétée avec le profil de son adresse, sans altérer le décodage de l'autre

### Requirement: Distinction entre commande émise et effet physique

Le décodeur SHALL qualifier tout événement de sortie comme une **commande observée sur le bus**, et
SHALL n'affirmer en aucun cas qu'une sortie a physiquement commuté, cette information n'étant pas
présente dans le protocole.

#### Scenario: Vocabulaire non ambigu dans la sortie

- **WHEN** un événement de sortie est restitué à l'opérateur, en mode texte ou en NDJSON
- **THEN** il est formulé comme une commande observée, accompagné de l'état d'acquittement de la trame, et jamais comme un état de sortie confirmé

### Requirement: Résumé d'état commandé reconstruit et marqué comme inféré

Le décodeur SHALL pouvoir reconstruire, à partir de la séquence de commandes observée, un état
**commandé** cumulé par BA et par sortie, et SHALL marquer explicitement cet état comme inféré depuis le
début de la capture, donc incomplet si la capture n'a pas démarré à la mise sous tension.

#### Scenario: État inféré signalé comme partiel

- **WHEN** une session de capture démarre alors que l'installation fonctionne déjà
- **THEN** le résumé d'état affiche les sorties jamais commandées depuis le début de la capture comme « inconnues », et non comme « éteintes »
