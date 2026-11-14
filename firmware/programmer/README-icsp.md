# Moteur ICSP des BA — PIC16F946

`icsp.c` est un moteur C11 sans dépendance au SDK Pico. Il produit les séquences
ICSP réelles à travers une interface de callbacks, mais **aucun adaptateur GPIO
qualifié ne lui est raccordé et aucun essai sur BA n'est déclaré réalisé**.
Le firmware publié doit donc conserver `board_qualified=false` et ne pas exposer
une option USB permettant de lever cette condition. Les tests exécutent un modèle
de cible sur l'hôte, pas une simulation des tensions ou du superviseur NCP803.

## Architecture

`icsp_init` installe les callbacks et applique immédiatement `safe_off`.
`icsp_open` vérifie les conditions d'entrée, lit l'identité du composant,
les quatre identifiants utilisateur, CONFIG et les deux mots de calibration.
Il conserve aussi l'EEPROM si CPD permet sa lecture. `icsp_read` effectue une
lecture adressée ; une lecture protégée est refusée plutôt que présentée comme
une sauvegarde remplie de zéros. `icsp_program` valide l'image entière avant
l'effacement, programme puis vérifie toutes les zones prises en charge.
`icsp_close` retire la haute tension et désactive l'interface.

Aucune commande brute publique n'autorise un contournement des contrôles.
Les adresses de l'API sont des **adresses de mots PIC**, pas des octets Intel HEX.

| Zone | Lecture | Écriture dans cette version |
| --- | --- | --- |
| Programme `0000..1FFF` | Si CP=1 | Image dense complète de 8192 mots, 14 bits |
| Identifiants `2000..2003` | Oui | Préservés, pas modifiés |
| Device ID `2006` | Oui, famille `146x` exigée | Interdite |
| CONFIG `2007` | Oui | Dernier mot écrit, bit 13 à 1, CP/CPD maintenus à 1 |
| Calibration `2008..2009` | Sauvegarde et comparaison | Jamais écrite |
| EEPROM `2100..21FF` | Si CPD=1 | Préservée par défaut ; remplacement explicite de 256 octets |
| Réservé / hors limites | Refusé | Refusé |

Le chargeur hôte doit remplir les trous de programme par `0x3FFF`, normaliser
les mots du HEX sur 14 bits après validation, et refuser une demande de modification
d'identifiants utilisateur non prise en charge par cette API. L'inspection HEX
seule n'autorise jamais une connexion matérielle.

## Entrée et arrêt électrique

Deux profils existent dans `icsp_policy` :

- **VPP-first** : exige une alimentation cible réellement commutable. VDD et
  MCLR sont mesurés bas avant VPP, VPP est contrôlée avant de monter VDD.
- **VDD-first** : cible alimentée extérieurement, configuration actuelle connue
  et compatible exigée. Elle est comparée au CONFIG réellement relu. **MCLRE=1 est obligatoire**
  pour cette configuration et pour la nouvelle image : avec VDD externe,
  `safe_off` doit pouvoir maintenir le PIC en reset en gardant MCLR bas. Cette
  restriction est volontairement plus forte que les seules conditions d’entrée
  de DS41244F ; elle exclut aussi MCLRE=0 avec une horloge externe.

La présence de la configuration dans un fichier à programmer ne prouve pas la
configuration actuellement présente sur le PIC. Le profil VDD-first ne doit pas
être choisi sur cette seule base. Une cible avec INTOSC et MCLR interne peut
exiger le profil VPP-first.

Le callback `vpp(false)` doit maintenir MCLR au niveau bas ; désactiver seulement
un convertisseur sans décharger la ligne ne suffit pas. `safe_off` est obligatoire,
idempotent et indépendant des callbacks ordinaires : VDD coupée d'abord si
contrôlée, VPP retirée/déchargée, PGC/PGD inactifs. Avec VDD externe, maintenir
MCLR bas. Le moteur ne comporte aucune commande de reprise d'exécution du BA.

`alive` doit combiner échéance de session, annulation/déconnexion USB, service du
watchdog et défauts matériels. Il doit également vérifier que seul le port BA
est sélectionné et que le port BP reste inactif ; la perte de cet interverrouillage
doit immédiatement retourner faux. Les attentes sont découpées en pas d'au plus
100 µs ; les tensions sont contrôlées avant chaque commande et pendant les longues
attentes. Une erreur ou annulation appelle `safe_off`, invalide la session et
exige une nouvelle initialisation. Les callbacks doivent être bornés et ne pas
bloquer indéfiniment : le cœur C ne peut interrompre un callback qui ne revient pas.

## Programmation et préservation

Une programmation exige `allow_programming` et `backup_verified`, établis par
l'orchestrateur après sauvegarde persistante vérifiée. Ce sont des préconditions
d'intégration, pas une preuve que le moteur a lui-même enregistré une sauvegarde.
L'autorisation est consommée au premier essai d'effacement.

Avant effacement, le moteur compare identité, configuration, identifiants,
calibration et EEPROM au relevé d'ouverture. Il refuse les cibles CP=0 ou CPD=0,
ainsi que les images activant l'une de ces protections. Aucun effacement de
« déverrouillage » n'est implémenté. L'effacement programme est émis depuis
l'espace programme, ce qui conserve les identifiants utilisateur ; CPD=1 permet
de conserver l'EEPROM. Celle-ci est ensuite comparée, ou programmée octet par
octet si un remplacement complet est explicitement demandé.

Les mots programme sont écrits un par un avec vérification immédiate, puis CONFIG
en dernier. Une sortie/rentrée du mode programmation efface les huit latches
après CONFIG, sans charger ni programmer les adresses de calibration. La dernière
passe compare **tout le programme et toute l'EEPROM**, en plus des identifiants
et calibrations. `verified=true` n'est défini qu'au terme de cette passe. Toute
interruption après début d'effacement peut laisser une cible partiellement
programmée ; le rapport garde `erase_started=true` et n'annonce aucun succès.

## Provenance du protocole

Source primaire : [Microchip DS41244F, PIC16F91X/946 Memory Programming Specification](https://ww1.microchip.com/downloads/en/DeviceDoc/41244F.pdf), révision F d'octobre 2009.

| Implémentation | Référence dans la spécification |
| --- | --- |
| Adresses et calibration non effacée | §2, pages 6–8 |
| Entrées VPP-first/VDD-first | §3, page 9 |
| Écriture un mot, remise à zéro des latches | §3.1.3–3.1.4, page 11 |
| Effacement depuis programme / préservation IDs | §3.1.5, page 11 |
| Commandes 6 bits LSb-first, 16 cycles de données | Tableau 3-1 et figures 3-4 à 3-9, pages 12–15 |
| Début de programmation interne, EEPROM auto-effacée | §3.1.6.7, page 16 |
| Vérification calibration | Figure 3-22, page 25 |
| Bits CONFIG, identification 146x, protections | §4–5, pages 26–29 |
| Tensions et délais | Tableau 6-1, page 31 |

Le code utilise des phases de 1 µs, 5 µs après les changements d'alimentation,
6 ms après effacement, 3 ms pour un mot programme/configuration, 6 ms pour un
octet EEPROM et 100 µs supplémentaires avant comparaison. La fenêtre électrique
retenue pour les BA est 4,5–5,5 V sur VDD et 10–12 V sur VPP. Le front VPP
≤1 µs, les niveaux, les courants et le chemin MCLR/NCP803 exigent une mesure
physique ; les temporisations logicielles ne les démontrent pas.

## Vérification

```sh
uv run --extra dev pytest tests/test_icsp_native.py -q
```

Le test compile en C11 strict avec UndefinedBehaviorSanitizer et exécute un modèle
indépendant observant les fronts PGC/PGD : valeurs de commandes, encadrement des
mots, retournement de direction, temps minimaux, banques d'adresses, image dense,
EEPROM préservée/remplacée, calibration altérée, mauvais composant, protections,
image invalide avant effacement, autorisation consommée, annulation, perte de
l’exclusivité BA/BP et chute de
VDD pendant effacement. Ce test ne remplace ni le test des fronts réels, ni la
qualification de l'adaptateur, ni la programmation/relecture des trois BA sur banc.
