"""Sémantique domotique des trames BP→BA.

Les résultats sont des **commandes observées sur le bus** : le protocole ne
renvoie jamais l'état physique des sorties.

Références firmware BA v1.7 (``slavenode.c``, ``hard.c``) :

- FORCAGE_SORTIES : octets 1/3 lampes à éteindre (bits 0-7 / 8-15), 2/4 lampes à
  allumer, 5 variateurs à éteindre, 6 variateurs à allumer, 7 volets sens 1
  (montée/ouverture), 8 volets sens 2 (descente/fermeture). Extinction
  prioritaire pour lampes et variateurs, montée prioritaire pour les volets.
- CONF_SORTIES : un octet de mode par variateur (``& 0x07``).
- TPS_EXTINCTION : un octet par relais lampe (minutes, 0 = pas d'extinction auto).
- TPS_ACTION : un octet par volet (secondes).
- ACTIONS : bit 0 secouru/sauvegarde, bit 1 blocage volets, bit 2 forçage
  allumage. Ordre des bits à confirmer sur capture réelle (tâche 6.3).
"""

from __future__ import annotations

from dataclasses import dataclass

FRAME_NAMES = {
    1: "FORCAGE_SORTIES",
    2: "CONF_SORTIES",
    3: "TPS_EXTINCTION",
    4: "TPS_ACTION",
    5: "ACTIONS",
}

#: Longueur sur le fil (code + charge utile + CRC), hors octet d'adresse.
FRAME_LENGTHS = {1: 11, 2: 11, 3: 19, 4: 11, 5: 4}

BA_NAMES = {0x11: "pièces de vie", 0x12: "chambres", 0x13: "pièces d'eau"}
BA_NUMBERS = {0x11: 0, 0x12: 1, 0x13: 2}


@dataclass(frozen=True)
class Profile:
    lamps: int
    dimmers: int
    shutters: int


#: Profils relevés dans ``hard.c`` des BA v1.7 (uc_RM_NB, uc_VARIATEUR_NB, uc_RB_NB / 2).
DEFAULT_PROFILES = {
    0x11: Profile(lamps=5, dimmers=3, shutters=6),
    0x12: Profile(lamps=7, dimmers=4, shutters=5),
    0x13: Profile(lamps=13, dimmers=1, shutters=4),
}

ACTION_FLAGS = {0: "secouru / sauvegarde d'état", 1: "blocage des volets", 2: "forçage de l'allumage"}

DIMMER_MODES = {0: "TOR avec rampe", 1: "gradateur", 2: "TOR sans rampe"}


def ba_label(addr: int) -> str:
    if addr in BA_NAMES:
        return f"BA {BA_NUMBERS[addr]} ({BA_NAMES[addr]})"
    return f"adresse 0x{addr:02X} (non résolue)"


def _bits(value: int, width: int = 8) -> list[int]:
    return [i for i in range(width) if value & (1 << i)]


def decode_payload(code: int, payload: bytes, addr: int, profiles: dict[int, Profile] | None = None):
    """Retourne ``(commands, anomalies, fields)`` pour une trame de longueur conforme."""
    profiles = profiles or DEFAULT_PROFILES
    profile = profiles.get(addr)
    commands: list[dict] = []
    anomalies: list[str] = []
    fields: dict = {}

    def check(kind: str, index: int, limit: int | None) -> bool:
        if limit is not None and index >= limit:
            anomalies.append(f"index de sortie hors plage : {kind} {index} (profil : {limit})")
            return False
        return True

    if code == 1:
        off = payload[0] | (payload[2] << 8)
        on = payload[1] | (payload[3] << 8)
        dim_off, dim_on, up, down = payload[4], payload[5], payload[6], payload[7]
        for i in _bits(on | off, 16):
            if not check("lampe", i, profile.lamps if profile else None):
                continue
            conflict = bool(on & off & (1 << i))
            commands.append({"type": "lampe", "index": i, "action": "OFF" if off & (1 << i) else "ON", "conflict": conflict})
        for i in _bits(dim_on | dim_off):
            if not check("variateur", i, profile.dimmers if profile else None):
                continue
            conflict = bool(dim_on & dim_off & (1 << i))
            commands.append({"type": "variateur", "index": i, "action": "OFF" if dim_off & (1 << i) else "ON", "conflict": conflict})
        for i in _bits(up | down):
            if not check("volet", i, profile.shutters if profile else None):
                continue
            conflict = bool(up & down & (1 << i))
            commands.append({"type": "volet", "index": i, "action": "montée/ouverture" if up & (1 << i) else "descente/fermeture", "conflict": conflict})
        if not commands and not anomalies:
            fields["note"] = "aucune sortie commandée"
    elif code == 2:
        count = profile.dimmers if profile else len(payload)
        fields["modes_variateurs"] = [
            {"index": i, "mode": b & 0x07, "libelle": DIMMER_MODES.get(b & 0x07, "inconnu")} for i, b in enumerate(payload[:count])
        ]
        fields["bourrage"] = payload[count:].hex()
        fields["note"] = "écriture EEPROM côté BA si la valeur change"
    elif code == 3:
        count = profile.lamps if profile else len(payload)
        fields["extinction_min"] = [
            {"lampe": i, "minutes": b, "libelle": "pas d'extinction automatique" if b == 0 else f"{b} min"} for i, b in enumerate(payload[:count])
        ]
        fields["bourrage"] = payload[count:].hex()
        fields["note"] = "écriture EEPROM côté BA si la valeur change"
    elif code == 4:
        count = profile.shutters if profile else len(payload)
        fields["action_volets_s"] = [{"volet": i, "secondes": b} for i, b in enumerate(payload[:count])]
        fields["bourrage"] = payload[count:].hex()
        fields["note"] = "écriture EEPROM côté BA si la valeur change"
    elif code == 5:
        value = payload[0]
        fields["octet"] = value
        for bit, name in ACTION_FLAGS.items():
            commands.append({"type": "drapeau", "index": bit, "action": "actif" if value & (1 << bit) else "inactif", "name": name, "conflict": False})
        reserved = value & 0xF8
        if reserved:
            anomalies.append(f"bits réservés positionnés dans ACTIONS : 0x{value:02X}")
    return commands, anomalies, fields


class StateTracker:
    """État **commandé** cumulé par BA, inféré depuis le début de la capture."""

    def __init__(self, profiles: dict[int, Profile] | None = None) -> None:
        self.profiles = profiles or DEFAULT_PROFILES
        self.state: dict[int, dict[tuple[str, int], str]] = {}
        self.flags: dict[int, int] = {}

    def apply(self, addr: int, commands: list[dict]) -> list[dict]:
        """Applique des commandes validées ; retourne les transitions de drapeaux ACTIONS."""
        transitions = []
        st = self.state.setdefault(addr, {})
        flag_cmds = [c for c in commands if c["type"] == "drapeau"]
        if flag_cmds:
            value = sum(1 << c["index"] for c in flag_cmds if c["action"] == "actif")
            previous = self.flags.get(addr)
            if previous is not None:
                for bit, name in ACTION_FLAGS.items():
                    if (previous ^ value) & (1 << bit):
                        transitions.append({"flag": name, "from": bool(previous & (1 << bit)), "to": bool(value & (1 << bit))})
            self.flags[addr] = value
        for c in commands:
            if c["type"] != "drapeau":
                st[(c["type"], c["index"])] = c["action"]
        return transitions

    def summary(self) -> dict:
        out = {"inferred": True, "note": "état commandé inféré depuis le début de la capture ; « inconnu » = jamais commandé", "ba": {}}
        for addr, profile in sorted(self.profiles.items()):
            st = self.state.get(addr, {})
            out["ba"][f"0x{addr:02X}"] = {
                "label": ba_label(addr),
                "lampes": [st.get(("lampe", i), "inconnu") for i in range(profile.lamps)],
                "variateurs": [st.get(("variateur", i), "inconnu") for i in range(profile.dimmers)],
                "volets": [st.get(("volet", i), "inconnu") for i in range(profile.shutters)],
            }
        return out
