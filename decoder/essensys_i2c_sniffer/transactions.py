"""Reconstruction des transactions I2C à partir des événements sigrok.

Une transaction va d'un START au STOP suivant. Elle contient une ou plusieurs
phases (une par octet d'adresse) séparées par des repeated START. Dans le
protocole Essensys : phase d'écriture (trame) puis, après repeated START, phase
de lecture de 5 octets (réponse du BA).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .annotations import Event


@dataclass
class Phase:
    direction: str  # "W" ou "R"
    addr: int
    addr_ack: bool | None = None
    data: list[int] = field(default_factory=list)
    acks: list[bool | None] = field(default_factory=list)


@dataclass
class Transaction:
    start: int
    end: int = -1
    phases: list[Phase] = field(default_factory=list)
    stopped: bool = False
    anomalies: list[str] = field(default_factory=list)


class TransactionBuilder:
    """Machine à états : consomme des ``Event`` et produit des ``Transaction`` terminées."""

    def __init__(self) -> None:
        self._tx: Transaction | None = None
        self._last_kind: str | None = None  # "addr" ou "data" : cible du prochain ACK/NACK

    @property
    def open_start(self) -> int | None:
        """Échantillon de début de la transaction en cours, s'il y en a une."""
        return self._tx.start if self._tx else None

    def feed(self, event: Event) -> Iterator[Transaction]:
        kind = event.kind
        if kind == "start":
            if self._tx is not None:
                self._tx.anomalies.append("trame interrompue : START sans STOP")
                self._tx.end = event.start
                yield self._tx
            self._tx = Transaction(start=event.start)
            self._last_kind = None
        elif kind == "rstart":
            if self._tx is None:
                self._tx = Transaction(start=event.start, anomalies=["repeated START sans START"])
            self._last_kind = None
        elif kind in ("addr_w", "addr_r"):
            if self._tx is None:
                self._tx = Transaction(start=event.start, anomalies=["adresse sans START"])
            self._tx.phases.append(Phase("W" if kind == "addr_w" else "R", event.value or 0))
            self._last_kind = "addr"
        elif kind in ("data_w", "data_r"):
            phase = self._current_phase(event)
            if phase is not None:
                phase.data.append(event.value or 0)
                phase.acks.append(None)
                self._last_kind = "data"
        elif kind in ("ack", "nack"):
            phase = self._current_phase(event)
            if phase is not None:
                value = kind == "ack"
                if self._last_kind == "addr":
                    phase.addr_ack = value
                elif self._last_kind == "data" and phase.acks:
                    phase.acks[-1] = value
                self._last_kind = None
        elif kind == "stop":
            if self._tx is not None:
                self._tx.end = event.end
                self._tx.stopped = True
                yield self._tx
                self._tx = None
            self._last_kind = None
        elif kind == "invalid":
            if self._tx is not None:
                self._tx.anomalies.append(f"annotation non reconnue : {event.raw}")

    def flush(self, end_sample: int) -> Iterator[Transaction]:
        if self._tx is not None:
            self._tx.anomalies.append("trame interrompue : fin de capture sans STOP")
            self._tx.end = end_sample
            yield self._tx
            self._tx = None

    def _current_phase(self, event: Event) -> Phase | None:
        if self._tx is None or not self._tx.phases:
            if self._tx is not None:
                self._tx.anomalies.append(f"octet hors phase à l'échantillon {event.start}")
            return None
        return self._tx.phases[-1]


def build(events: Iterable[Event], end_sample: int = -1) -> list[Transaction]:
    builder = TransactionBuilder()
    out: list[Transaction] = []
    for event in events:
        out.extend(builder.feed(event))
    out.extend(builder.flush(end_sample))
    return out
