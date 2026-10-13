# Corpus de référence

Généré par `tools/make_corpus.py`. Signaux synthétiques à 1 MHz (bit 0 = SCL, bit 1 = SDA), annotations par le décodeur I2C de sigrok.

| Scénario | Description |
|---|---|
| `forcage_sorties_ok` | FORCAGE_SORTIES vers 0x11 : lampe 0 ON puis OFF, réponses validées |
| `conf_sorties_ok` | CONF_SORTIES vers 0x12 : modes des 4 variateurs + bourrage |
| `tps_extinction_ok` | TPS_EXTINCTION vers 0x13 : minutes par relais lampe |
| `tps_action_ok` | TPS_ACTION vers 0x11 : secondes par volet |
| `actions_ok` | ACTIONS vers 0x12 : transition du drapeau blocage des volets |
| `address_nack` | NACK d'adresse : BA chambres absent |
| `crc_faux` | CRC de requête faux : le BA renvoie 00 00 en écho |
| `repetitions_abandon` | 3 tentatives NACK vers 0x13 puis silence : abandon du maître |
| `ligne_bloquee` | SDA maintenue basse 15 ms |
| `cas_installation_2026_10` | Cas observé le 2026-10-13 : 0x11 répond, 0x12 et 0x13 muets (signal synthétique) |
