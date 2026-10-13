"""Détection des lignes SDA/SCL maintenues au niveau bas.

Entrée : échantillons logiques bruts au format ``sigrok -O binary`` (un octet
par échantillon, bit n = voie Dn). Les recherches se font avec
``bytes.translate`` et ``bytes.find`` pour suivre 1 Méch/s en Python pur.
"""

from __future__ import annotations

from dataclasses import dataclass


def _table(bit: int) -> bytes:
    return bytes((1 if (b >> bit) & 1 else 0) for b in range(256))


@dataclass
class _Run:
    start: int | None = None  # échantillon du début du niveau bas en cours


class LineWatch:
    def __init__(self, lines: dict[str, int], samplerate: int, threshold_ms: float = 10.0) -> None:
        """``lines`` : nom → numéro de bit, par exemple ``{"SCL": 0, "SDA": 1}``."""
        self.samplerate = samplerate
        self.threshold = int(samplerate * threshold_ms / 1000)
        self.tables = {name: _table(bit) for name, bit in lines.items()}
        self.runs = {name: _Run() for name in lines}
        self.position = 0  # nombre d'échantillons déjà traités

    def feed(self, chunk: bytes) -> list[dict]:
        events = []
        base = self.position
        for name, table in self.tables.items():
            levels = chunk.translate(table)
            run = self.runs[name]
            pos = 0
            n = len(levels)
            while pos < n:
                if run.start is None:
                    low = levels.find(b"\x00", pos)
                    if low < 0:
                        break
                    run.start = base + low
                    pos = low
                high = levels.find(b"\x01", pos)
                if high < 0:
                    break
                event = self._close(name, run, base + high)
                if event:
                    events.append(event)
                pos = high
        self.position += len(chunk)
        events.sort(key=lambda e: e["sample"])
        return events

    def flush(self) -> list[dict]:
        events = []
        for name, run in self.runs.items():
            event = self._close(name, run, self.position, ongoing=True)
            if event:
                events.append(event)
        return sorted(events, key=lambda e: e["sample"])

    def _close(self, name: str, run: _Run, end: int, ongoing: bool = False) -> dict | None:
        start = run.start
        run.start = None
        if start is None:
            return None
        length = end - start
        if length <= self.threshold:
            return None
        return {
            "type": "line_stuck",
            "sample": start,
            "end_sample": end,
            "line": name,
            "duration_ms": round(length * 1000 / self.samplerate, 3),
            "ongoing_at_end": ongoing,
            "summary": f"{name} bloquée au niveau bas pendant {length * 1000 / self.samplerate:.1f} ms"
            + (" (toujours basse en fin de capture)" if ongoing else ""),
        }
