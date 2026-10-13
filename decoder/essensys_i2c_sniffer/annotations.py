"""Lecture des annotations du décodeur I2C de sigrok.

Format produit par ``sigrok-cli -P i2c:scl=..:sda=.. -A i2c=... --protocol-decoder-samplenum`` ::

    210-210 i2c-1: Start
    235-375 i2c-1: Address write: 12
    395-415 i2c-1: NACK
    1500-1500 i2c-1: Start repeat
    1700-1860 i2c-1: Data read: 05
    2070-2070 i2c-1: Stop

Les lignes « Write » / « Read » (bit R/W) et les lignes d'autres décodeurs
sont ignorées. Une ligne tronquée ou inconnue produit un événement ``invalid``
au lieu d'une exception.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LINE = re.compile(r"^\s*(?P<start>\d+)-(?P<end>\d+)\s+(?P<pd>[\w.-]+):\s*(?P<text>.*?)\s*$")
_VALUE = re.compile(r"^(Address write|Address read|Data write|Data read):\s*([0-9A-Fa-f]{1,2})$")

#: Correspondance texte sigrok → type d'événement.
_SIMPLE = {
    "Start": "start",
    "Start repeat": "rstart",
    "Repeat start": "rstart",
    "Stop": "stop",
    "ACK": "ack",
    "NACK": "nack",
}
_VALUED = {
    "Address write": "addr_w",
    "Address read": "addr_r",
    "Data write": "data_w",
    "Data read": "data_r",
}
_IGNORED = {"Write", "Read"}


@dataclass(frozen=True)
class Event:
    kind: str  # start, rstart, stop, ack, nack, addr_w, addr_r, data_w, data_r, invalid
    start: int
    end: int
    value: int | None = None
    raw: str | None = None


def parse_line(line: str, decoder_prefix: str = "i2c") -> Event | None:
    """Convertit une ligne d'annotation en ``Event`` ; ``None`` si la ligne est à ignorer."""
    if not line.strip():
        return None
    match = _LINE.match(line)
    if not match:
        return Event("invalid", -1, -1, raw=line.rstrip("\n"))
    if not match["pd"].startswith(decoder_prefix):
        return None
    start, end, text = int(match["start"]), int(match["end"]), match["text"]
    if text in _IGNORED:
        return None
    if text in _SIMPLE:
        return Event(_SIMPLE[text], start, end)
    valued = _VALUE.match(text)
    if valued:
        return Event(_VALUED[valued[1]], start, end, int(valued[2], 16))
    if text.lower().startswith("warning"):
        return Event("invalid", start, end, raw=text)
    return Event("invalid", start, end, raw=text)


def sort_key(event: Event) -> tuple[int, int]:
    # sigrok émet le bit R/W avant l'adresse ; on remet l'ordre par échantillon de début.
    return (event.start, event.end)
