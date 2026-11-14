# Moteur BDM BP — lecture de la flash interne

`bdm.c` est un moteur C portable pour le **MCF52259 du BP SC944D**, avec
entrées/sorties injectées. Il implémente les échanges série réels, pas un
transport qui retourne systématiquement des données simulées. Les tests
utilisent un interlocuteur simulé ; **aucun BP ni étage électrique réel n'a
été validé**. Le firmware diagnostic de la carte conserve la qualification à
faux et n'expose pas ces opérations sur l'USB.

## Références vérifiées

- [NXP, MCF52259RM rév. 4](https://www.nxp.jp/docs/en/reference-manual/MCF52259RM.pdf),
  §33.4.1.2–33.4.1.4 et figures 33-12 à 33-16 : synchronisation, format série et
  réponses différées ; §33.4.1.5.3, .7, .8 et .14 : READ, GO, NOP, RDMREG ;
  §33.3.2 : CSR et effets de sa lecture. Copie consultée le 2026-11-14,
  SHA256 `b02fb25c7301b2c59185290c328ed1a92677a5d606d028e443f4d8e54613b3fe`.
- [NXP, MCF52259 Data Sheet rév. 5](https://www.nxp.com/docs/en/data-sheet/MCF52259.pdf),
  tableau 13 : alimentation 3,0–3,6 V. La mesure doit inclure son incertitude
  dans la qualification ; les bornes logicielles ne sont pas une protection
  contre les surtensions.
- `essensys-bdm-programmer/docs/R1-research-notes.md` : J33 et JC1 tirés du
  schéma SC944D, feuille Cœur. Le dépôt contient encore des transports matériels
  non implémentés ; ce nouveau moteur ne rend pas son CLI opérationnel.

## Contrat du transport

| Opération | Encodage / règle |
| --- | --- |
| Trame | 17 bits, MSB d'abord ; bit réservé transmis à zéro |
| Réponse | S=0 : donnée ; S=1/0000 : attente ; S=1/0001 : erreur bus ; S=1/FFFF : illégale |
| Lecture flash | `1900` octet, `1940` mot, `1980` long ; adresse absolue MSW puis LSW |
| CSR | `2D80`, résultat 32 bits MSW puis LSW |
| NOP | `0000`, utilisé pendant l'attente et pour terminer les réponses |
| Reprise explicite | `0C00` (GO), acquittement puis vérification ALLPST |

Le moteur traite les réponses simultanées au mot suivant : une extension de
READ reçoit une attente, puis les résultats sont récupérés par NOP. Il ne
considère jamais `FFFF` avec S=0 comme un marqueur de fin de données.

DSI est placé pendant DSCLK bas ; DSO est lu **après** la phase haute et les
synchronisations internes. Chaque demi-période réserve au moins cinq cycles
de la borne basse garantie de PSTCLK, avec au moins 32 cycles entre trames.
Cette marge est volontairement supérieure à la limite théorique PSTCLK/5.
Le paramètre `pstclk_min_hz` doit être justifié pour le BP dans l'état visé ;
la fréquence nominale 80 MHz ne suffit pas comme preuve. Exemple de test :
PSTCLK ≥ 1 MHz, phases de 5 µs, pause de 32 µs entre trames. Ce n'est pas une
fréquence déjà qualifiée sur le BP.

## Sessions et qualification

1. Initialiser un objet neuf/inactif avec `bdm_init`. Cette fonction n'actionne
   aucune broche ; elle ne remplace pas `bdm_close` sur un objet actif.
2. `bdm_open` refuse la mise en service tant que la carte, les niveaux, le mode
   BDM de JC1 et l'alignement après un reset de cible ne sont pas confirmés.
   L'état de sélection exclusive BP/VPP coupée est contrôlé par le callback
   `target`. Aucune commande ni demande de reset n'est envoyée à l'ouverture.
3. `bdm_halt` est une action explicite : BKPT est asserté et ALLPST doit
   confirmer l'arrêt. Deux NOP vérifient ensuite le dialogue. Ils ne peuvent
   pas retrouver l'alignement d'une trame interrompue ; le reset préalable
   reste indispensable. Le moteur ne génère pas ce reset.
4. `bdm_read_csr` vérifie HRL=9 (révision B+ du module de debug). **Ce n'est
   pas une identification unique du MCF52259.** Lire CSR efface certains
   indicateurs d'arrêt/breakpoint ; sa valeur est rapportée comme diagnostic.
   L'arrêt est surveillé par ALLPST, pas par les bits historiques du CSR.
5. `bdm_read_flash` lit uniquement `00000..7FFFF`, par blocs de 1 à 256 octets.
   Les accès non alignés sont découpés en octets/mots/longs sans aligner
   silencieusement l'adresse vers une autre zone. Le tampon utilisateur n'est
   modifié qu'après réussite du bloc entier.
6. `bdm_resume` est la seule opération qui envoie GO. Elle libère BKPT,
   contrôle l'acquittement et le retour d'ALLPST à zéro, puis ferme la session.
   `bdm_close` et les défauts libèrent seulement les sorties. **Ils ne
   redémarrent pas le BP : le processeur peut rester arrêté.** Le champ
   `may_be_halted` conserve cette possibilité jusqu'à une reprise vérifiée.

Un arrêt du BP interrompt l'exécution de son application. Ces opérations sont
réservées au banc isolé ; aucune lecture BDM n'est qualifiée de capture I2C
passive. Après défaut/fermeture, une nouvelle confirmation de reset et une
nouvelle initialisation sont nécessaires avant réouverture.

Les callbacks doivent assurer l'exclusion BP/BA et les niveaux sans dépendre
seulement du programme. `release` désactive l'étage de sortie avant de libérer
BKPT ; il ne doit jamais activer RESET, VPP ou GO. Le retour RESET de la cible utilise une entrée dédiée, distincte de la commande
open-drain. Le futur adaptateur doit mémoriser toute assertion de RESET survenue
pendant la session (par interruption/flag GPIO), même si la ligne est remontée
avant le prochain callback ; la session reste invalide jusqu'à requalification.
Les mesures, cancellation USB et délai sont revérifiés pendant les trames. Attentes et opérations ont
une limite en temps et en nombre d'itérations. L'adaptateur matériel doit
assurer le repli même après reset/watchdog du RP2350.

## Fonctions volontairement indisponibles

Pas d'écriture de mémoire ou registre, effacement flash, modification de PC,
reset cible, déverrouillage de sécurité, accès JTAG, ni commande brute libre.
La lecture interne de 512 Kio ne sauvegarde ni la flash SPI externe ni
l'EEPROM du BP. Aucune identité individuelle de carte n'est déduite du CSR.

La programmation BP reste un travail séparé : identification fiable,
algorithme CFM validé, sauvegarde vérifiée et liée à la cible, préservation
bootloader/configuration/persistance, contrôle de l'image et récupération
après coupure. La présence des opcodes WRITE dans le manuel n'est pas une
implémentation de programmation flash.

## Vérification

```sh
uv run --extra dev pytest -q tests/test_bdm_native.py
```

28 cas compilent le moteur C avec avertissements stricts et UBSan : vecteurs
série indépendants, ordre des bits/octets, attentes, valeur `FFFF`, limites
flash, erreurs aux deux mots, conditions initiales, annulation et défauts
pendant une trame, timeout, arguments invalides en session active et reprise explicite. Ces tests n'émulent pas les
synchroniseurs matériels, le câblage J33 ou l'étage d'adaptation.
