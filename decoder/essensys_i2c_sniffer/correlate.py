"""Corrélation entre les journaux du backend CM5 et une capture du bus.

Entrée backend : sortie de ``docker logs essensys-backend`` exportée dans un
fichier par l'opérateur. L'outil ne se connecte jamais au CM5 et n'envoie rien.

Lignes utilisées ::

    2026/10/13 11:22:01 [GO] Sending Actions: {"_de67f":null,"actions":[{"guid":"…","params":[{"k":613,"v":"64"}, …]}]}
    2026/10/13 11:22:01 [GO] Action acknowledged: <guid>

Rappel : le BP acquitte ``/api/done`` **avant** d'envoyer l'ordre au BA par I2C.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_TS = r"(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
_SENDING = re.compile(_TS + r" .*?Sending Actions: (\{.*\})\s*$")
_ACK = re.compile(_TS + r" .*?Action acknowledged: ([0-9a-fA-F-]{8,})")

_PDV, _CHB, _PDE = 0x11, 0x12, 0x13
#: Index de la table d'échange → BA visé (scénario 605-622, configuration 494-589).
_INDEX_TO_BA: dict[int, int] = {}
for _k in (605, 606, 611, 612, 617, 620):
    _INDEX_TO_BA[_k] = _PDV
for _k in (607, 608, 613, 614, 618, 621):
    _INDEX_TO_BA[_k] = _CHB
for _k in (609, 610, 615, 616, 619, 622):
    _INDEX_TO_BA[_k] = _PDE
for _base, _ba in ((494, _PDV), (502, _CHB), (510, _PDE)):
    for _k in range(_base, _base + 8):
        _INDEX_TO_BA[_k] = _ba
for _base, _ba in ((518, _PDV), (534, _CHB), (550, _PDE)):
    for _k in range(_base, _base + 16):
        _INDEX_TO_BA[_k] = _ba
for _base, _ba in ((566, _PDV), (574, _CHB), (582, _PDE)):
    for _k in range(_base, _base + 8):
        _INDEX_TO_BA[_k] = _ba


def _parse_ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y/%m/%d %H:%M:%S")


@dataclass
class BackendAction:
    guid: str
    sent: datetime
    params: list[tuple[int, str]]
    acked: datetime | None = None
    targets: set[int] = field(default_factory=set)


def parse_backend_log(lines) -> list[BackendAction]:
    actions: dict[str, BackendAction] = {}
    for line in lines:
        m = _SENDING.search(line)
        if m:
            try:
                payload = json.loads(m[2])
            except json.JSONDecodeError:
                continue
            for act in payload.get("actions") or []:
                params = [(int(p["k"]), str(p["v"])) for p in act.get("params", [])]
                meaningful = [(k, v) for k, v in params if k != 590 and v not in ("0", "")]
                a = actions.setdefault(act["guid"], BackendAction(act["guid"], _parse_ts(m[1]), meaningful))
                a.targets = {_INDEX_TO_BA[k] for k, _ in meaningful if k in _INDEX_TO_BA}
            continue
        m = _ACK.search(line)
        if m and m[2] in actions:
            actions[m[2]].acked = _parse_ts(m[1])
    return sorted(actions.values(), key=lambda a: a.sent)


def correlate(actions: list[BackendAction], records: list[dict], capture_start: datetime, offset_s: float | None = None, window_s: float = 5.0) -> tuple[list[dict], float]:
    """Retourne les enregistrements ``correlation`` et le décalage d'horloge retenu (secondes)."""
    exchanges = [r for r in records if r.get("type") == "exchange" and r.get("addr")]

    def when(rec: dict) -> datetime:
        return capture_start + timedelta(milliseconds=rec["t_ms"])

    if offset_s is None:
        offset_s = 0.0
        for a in actions:
            ref = a.acked or a.sent
            candidates = [r for r in exchanges if int(r["addr"], 16) in a.targets]
            if candidates:
                nearest = min(candidates, key=lambda r: abs((when(r) - ref).total_seconds()))
                delta = (when(nearest) - ref).total_seconds()
                if abs(delta) <= 120:
                    offset_s = delta
                    break

    out = []
    for a in actions:
        ref = (a.acked or a.sent) + timedelta(seconds=offset_s)
        rec = {
            "type": "correlation",
            "guid": a.guid,
            "log_time": (a.acked or a.sent).strftime("%Y-%m-%d %H:%M:%S"),
            "params": [{"k": k, "v": v} for k, v in a.params],
            "acknowledged_by_bp": a.acked is not None,
            "expected": [f"0x{t:02X}" for t in sorted(a.targets)],
        }
        if not a.targets:
            rec["verdict"] = "aucun BA attendu (index hors bus BA)"
            out.append(rec)
            continue
        verdicts = []
        for target in sorted(a.targets):
            seen = [r for r in exchanges if int(r["addr"], 16) == target and -1.0 <= (when(r) - ref).total_seconds() <= window_s]
            label = f"0x{target:02X}"
            if any(r.get("status") == "validated" for r in seen):
                verdicts.append(f"{label} : transmise au BA (trame validée CRC ; la commutation physique n'est pas prouvée)")
            elif any(r.get("status") == "rejected" for r in seen):
                verdicts.append(f"{label} : rejetée par le BA")
            elif any(r.get("status") == "absent" for r in seen):
                verdicts.append(f"{label} : acquittée par le BP, non reçue par le BA (NACK d'adresse)")
            else:
                verdicts.append(f"{label} : aucune trame observée dans la fenêtre de {window_s:g} s")
            rec.setdefault("evidence", []).extend(r["sample"] for r in seen)
        rec["verdict"] = " ; ".join(verdicts)
        out.append(rec)
    return out, offset_s
