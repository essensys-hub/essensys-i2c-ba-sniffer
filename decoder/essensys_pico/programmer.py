"""Client du firmware de diagnostic intégré, sans commande de programmation.

Le firmware capture historique et ce service ont des schémas différents : une
réponse du mauvais UF2 est refusée avant de lui attribuer des capacités.
"""
from __future__ import annotations

import json
import time

from .transport import ProtocolError

SCHEMA = "essensys.programmer.v1"
COMMAND_KINDS = {"INFO": "info", "STATUS": "state", "STOP": "stopped"}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("clé JSON dupliquée")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"constante JSON interdite : {value}")


def diagnostic_request(port, command: str, *, clock=time.monotonic) -> dict:
    if command not in COMMAND_KINDS:
        raise ValueError("commande de diagnostic inconnue")
    wire = (command + "\n").encode("ascii")
    if port.write(wire) != len(wire):
        raise ProtocolError("commande USB incomplète")
    deadline = clock() + 5
    response = bytearray()
    while len(response) < 512:
        if clock() >= deadline:
            raise ProtocolError("délai de réponse du programmateur dépassé")
        byte = port.read(1)
        if not byte or len(byte) != 1:
            raise ProtocolError("réponse absente ou tronquée")
        response.extend(byte)
        if byte == b"\n":
            break
    else:
        raise ProtocolError("réponse du programmateur trop longue")
    try:
        result = json.loads(response, object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("réponse JSON invalide") from exc
    if not isinstance(result, dict) or result.get("schema") != SCHEMA:
        raise ProtocolError("firmware de diagnostic intégré attendu (UF2 incompatible)")
    if result.get("status") != "ok":
        raise ProtocolError(f"programmateur : {result.get('error', 'échec non précisé')}")
    if result.get("kind") != COMMAND_KINDS[command]:
        raise ProtocolError("réponse désynchronisée")
    if result.get("target") != "none" or result.get("programming_enabled") is not False:
        raise ProtocolError("état de diagnostic incohérent")
    if command == "INFO" and (result.get("mode") != "diagnostic-only"
                              or result.get("hardware_qualified") is not False
                              or result.get("ports") != ["bp-bdm", "ba-icsp"]
                              or result.get("capture") != "fx2"):
        raise ProtocolError("capacités de diagnostic incohérentes")
    if command == "STATUS" and (result.get("outputs_commanded_safe") is not True
                                or result.get("rails_measured") is not False):
        raise ProtocolError("état des interfaces incohérent")
    return result
