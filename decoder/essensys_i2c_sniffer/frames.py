"""Validation des échanges BP↔BA et suivi des répétitions.

Format (``ba.c``, ``ba_i2c.c`` du BP ; ``slavenode.c`` des BA) :

- requête  : ``[code][charge utile][CRC LO][CRC HI]``, CRC-16 sur code + charge utile ;
- réponse  : 5 octets ``[écho code][CRC calculé par le BA LO][HI][CRC des 3 premiers LO][HI]`` ;
  le BA renvoie ``00 00`` à la place de l'écho si le CRC reçu est faux ;
- le BP accepte l'échange si l'écho du code, le CRC de la réponse et l'écho du
  CRC sont corrects. Cela prouve que **la trame a été reçue et validée**, jamais
  que la sortie a commuté.
"""

from __future__ import annotations

from dataclasses import dataclass

from .crc import crc16
from .semantics import BA_NAMES, BA_NUMBERS, FRAME_LENGTHS, FRAME_NAMES, Profile, StateTracker, ba_label, decode_payload
from .transactions import Transaction


def _hex(data) -> str:
    return " ".join(f"{b:02X}" for b in data)


def decode_transaction(tx: Transaction, profiles: dict[int, Profile] | None = None) -> dict:
    """Transforme une transaction en enregistrement ``exchange`` (sans horodatage)."""
    rec: dict = {"type": "exchange", "sample": tx.start, "end_sample": tx.end, "anomalies": list(tx.anomalies)}
    if not tx.phases:
        rec.update(kind="empty")
        rec["anomalies"].append("transaction sans adresse")
        return rec
    first = tx.phases[0]
    addr = first.addr
    rec.update(addr=f"0x{addr:02X}", ba=BA_NUMBERS.get(addr), ba_name=BA_NAMES.get(addr), label=ba_label(addr))
    if addr not in BA_NAMES:
        rec["anomalies"].append("adresse hors plage 0x11-0x13")
    if first.direction != "W":
        rec.update(kind="read_only")
        rec["anomalies"].append("lecture sans trame d'écriture préalable")
        return rec
    if first.addr_ack is False:
        rec.update(kind="address_nack", status="absent", summary="BA absent : NACK d'adresse")
        return rec
    if first.addr_ack is None:
        rec["anomalies"].append("acquittement d'adresse non observé")

    request = bytes(first.data)
    rec["request"] = _hex(request)
    nacked = [i for i, a in enumerate(first.acks) if a is False]
    if nacked:
        rec["anomalies"].append(f"octet(s) de requête non acquittés par le BA : {nacked}")

    frame: dict = {}
    rec["frame"] = frame
    code = request[0] if request else None
    frame["code"] = code
    frame["name"] = FRAME_NAMES.get(code, "INCONNU") if code is not None else None
    expected_len = FRAME_LENGTHS.get(code) if code is not None else None
    frame["length"] = len(request)
    frame["expected_length"] = expected_len
    frame["length_ok"] = expected_len == len(request)
    crc_sent = None
    if code not in FRAME_NAMES:
        rec["anomalies"].append("code de trame inconnu : le BA rejettera la trame")
    elif not frame["length_ok"]:
        rec["anomalies"].append(f"longueur {len(request)} au lieu de {expected_len} : trame non interprétée")
    if len(request) >= 3:
        crc_sent = request[-2] | (request[-1] << 8)
        crc_expected = crc16(request[:-2])
        frame["crc"] = {"expected": f"0x{crc_expected:04X}", "received": f"0x{crc_sent:04X}", "ok": crc_expected == crc_sent}
        if crc_expected != crc_sent:
            rec["anomalies"].append(f"CRC de requête invalide (attendu 0x{crc_expected:04X}, reçu 0x{crc_sent:04X}) : le BA rejettera la trame")

    reads = [p for p in tx.phases[1:] if p.direction == "R"]
    if not reads:
        rec.update(kind="request_only", status="no_response", summary="requête sans phase de lecture")
    else:
        read = reads[0]
        response = bytes(read.data)
        rec["response"] = {"bytes": _hex(response)}
        if read.addr != addr:
            rec["anomalies"].append(f"lecture vers 0x{read.addr:02X} différente de l'adresse d'écriture")
        if read.addr_ack is False:
            rec.update(kind="exchange", status="absent", summary="BA absent à la lecture : NACK d'adresse")
        elif len(response) != 5:
            rec["anomalies"].append(f"réponse de {len(response)} octets au lieu de 5")
            rec.update(kind="exchange", status="invalid", summary="réponse incomplète")
        else:
            echo_ok = response[0] == code
            crc_resp_ok = crc16(response[:3]) == (response[3] | (response[4] << 8))
            echo_crc = response[1] | (response[2] << 8)
            echo_crc_ok = crc_sent is not None and echo_crc == crc_sent
            rec["response"].update(code_echo_ok=echo_ok, crc_ok=crc_resp_ok, crc_echo=f"0x{echo_crc:04X}", crc_echo_ok=echo_crc_ok)
            if echo_ok and crc_resp_ok and echo_crc_ok:
                rec.update(kind="exchange", status="validated", summary="trame reçue et validée CRC par le BA")
            else:
                reasons = []
                if not echo_ok:
                    reasons.append("écho du code faux")
                if not crc_resp_ok:
                    reasons.append("CRC de la réponse faux")
                if not echo_crc_ok:
                    reasons.append("écho CRC 0x0000 : le BA a rejeté le CRC" if echo_crc == 0 else f"écho CRC 0x{echo_crc:04X} ≠ CRC émis")
                rec.update(kind="exchange", status="rejected", summary="rejet côté BA : " + ", ".join(reasons))
        if len(reads) > 1 or len(tx.phases) > 2:
            rec["anomalies"].append("phases supplémentaires dans la transaction")

    if code in FRAME_NAMES and frame["length_ok"]:
        commands, anomalies, fields = decode_payload(code, request[1:-2], addr, profiles)
        rec["commands"] = commands
        rec["anomalies"].extend(anomalies)
        if fields:
            rec["fields"] = fields
    return rec


@dataclass
class _Pending:
    key: tuple
    rank: int
    sample: int
    addr: str


class RepeatTracker:
    """Détecte les répétitions d'une même trame et les abandons du maître.

    Le BP réémet la même trame tant qu'elle n'est pas acquittée, puis l'abandonne
    sans prévenir après ``uc_I2C_NB_REPETE`` échecs (``ba.c``).
    """

    def __init__(self, window_samples: int) -> None:
        self.window = window_samples
        self.pending: dict[str, _Pending] = {}

    def observe(self, rec: dict) -> list[dict]:
        """Annote ``rec`` (champ ``repeat``) et retourne les abandons échus avant lui."""
        out = self.expire(rec["sample"])
        addr = rec.get("addr")
        if addr is None:
            return out
        key = (rec.get("kind"), rec.get("request"))
        failed = rec.get("status") not in ("validated",)
        previous = self.pending.get(addr)
        if previous and previous.key == key and rec["sample"] - previous.sample <= self.window:
            rank = previous.rank + 1
            rec["repeat"] = {"rank": rank}
        else:
            rank = 0
        if failed:
            self.pending[addr] = _Pending(key, rank, rec["sample"], addr)
        else:
            self.pending.pop(addr, None)
        return out

    def expire(self, now_sample: int) -> list[dict]:
        out = []
        for addr, p in list(self.pending.items()):
            if now_sample - p.sample > self.window:
                kind, request = p.key
                out.append({
                    "type": "abandon",
                    "sample": p.sample + self.window,
                    "addr": addr,
                    "attempts": p.rank + 1,
                    "request": request,
                    "summary": "commande probablement abandonnée par le maître, jamais reçue par le BA",
                })
                del self.pending[addr]
        return out


class FrameDecoder:
    """Assemble décodage, répétitions et état commandé."""

    def __init__(self, samplerate: int, profiles: dict[int, Profile] | None = None, repeat_window_s: float = 2.0) -> None:
        self.profiles = profiles
        self.repeats = RepeatTracker(int(repeat_window_s * samplerate))
        self.state = StateTracker(profiles)
        self.nack_counts: dict[str, int] = {}

    def feed(self, tx: Transaction) -> list[dict]:
        rec = decode_transaction(tx, self.profiles)
        out = self.repeats.observe(rec)
        if rec.get("kind") == "address_nack" or rec.get("status") == "absent":
            self.nack_counts[rec["addr"]] = self.nack_counts.get(rec["addr"], 0) + 1
            rec["nack_count"] = self.nack_counts[rec["addr"]]
        if rec.get("status") == "validated" and "commands" in rec:
            transitions = self.state.apply(int(rec["addr"], 16), rec["commands"])
            if transitions:
                rec["flag_transitions"] = transitions
        out.append(rec)
        return out

    def flush(self, end_sample: int) -> list[dict]:
        return self.repeats.expire(end_sample)
