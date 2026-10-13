"""Assemblage : flux brut + annotations sigrok → enregistrements ordonnés.

Deux sources sont fusionnées par numéro d'échantillon :

- le flux brut (``sigrok -O binary``), pour la détection des lignes bloquées ;
- les annotations du décodeur I2C de sigrok, pour le protocole.

Un enregistrement n'est publié que lorsque les deux sources ont dépassé son
échantillon (filigrane). L'ordre de sortie ne dépend donc ni de la taille des
blocs ni du rythme d'arrivée : le rejeu d'une capture donne exactement les
mêmes enregistrements que le direct.
"""

from __future__ import annotations

import heapq
import itertools
import queue
import shutil
import subprocess
import threading
import time
from typing import Callable, Iterable, Iterator

from .annotations import parse_line
from .frames import FrameDecoder
from .linewatch import LineWatch
from .semantics import Profile
from .transactions import TransactionBuilder

#: Classes d'annotation du décodeur i2c de sigrok utilisées.
I2C_CLASSES = "start:repeat-start:stop:ack:nack:address-read:address-write:data-read:data-write:warnings"

_TYPE_ORDER = {"line_stuck": 0, "overflow": 0, "acquisition_warning": 0, "exchange": 1, "abandon": 2}


class Decoder:
    def __init__(
        self,
        samplerate: int,
        *,
        scl_bit: int = 0,
        sda_bit: int = 1,
        profiles: dict[int, Profile] | None = None,
        stuck_ms: float = 10.0,
        repeat_window_s: float = 2.0,
        use_raw: bool = True,
        use_annotations: bool = True,
    ) -> None:
        self.samplerate = samplerate
        self.builder = TransactionBuilder()
        self.frames = FrameDecoder(samplerate, profiles, repeat_window_s)
        self.linewatch = LineWatch({"SCL": scl_bit, "SDA": sda_bit}, samplerate, stuck_ms) if use_raw else None
        self.use_annotations = use_annotations
        self._heap: list = []
        self._seq = itertools.count()
        self._pd_mark = 0  # échantillon jusqu'où les annotations sont complètes

    # -- entrées -------------------------------------------------------
    def feed_raw(self, chunk: bytes) -> list[dict]:
        if self.linewatch is not None:
            for rec in self.linewatch.feed(chunk):
                self._push(rec)
        return self._release()

    def feed_annotation(self, line: str) -> list[dict]:
        event = parse_line(line)
        if event is None:
            return []
        if event.kind == "invalid" and event.start < 0:
            self._push({"type": "annotation_invalid", "sample": self._pd_mark, "raw": event.raw})
            return self._release()
        for tx in self.builder.feed(event):
            for rec in self.frames.feed(tx):
                self._push(rec)
        open_start = self.builder.open_start
        self._pd_mark = open_start if open_start is not None else max(self._pd_mark, event.end)
        return self._release()

    def mark_annotations_idle(self, upto: int) -> list[dict]:
        """Direct : sigrok, silencieux depuis un moment, a tout décodé jusqu'à ``upto`` (bus au repos)."""
        if self.builder.open_start is None:
            self._pd_mark = max(self._pd_mark, upto)
        return self._release()

    def note(self, rec: dict) -> list[dict]:
        rec.setdefault("sample", self.linewatch.position if self.linewatch else self._pd_mark)
        self._push(rec)
        return self._release()

    def finish(self) -> list[dict]:
        end = self.linewatch.position if self.linewatch else self._pd_mark
        for tx in self.builder.flush(end):
            for rec in self.frames.feed(tx):
                self._push(rec)
        for rec in self.frames.flush(end + 1):
            self._push(rec)
        if self.linewatch is not None:
            for rec in self.linewatch.flush():
                self._push(rec)
        out = []
        while self._heap:
            out.append(self._finalize(heapq.heappop(self._heap)[-1]))
        return out

    # -- fusion --------------------------------------------------------
    def _push(self, rec: dict) -> None:
        heapq.heappush(self._heap, (rec["sample"], _TYPE_ORDER.get(rec["type"], 3), next(self._seq), rec))

    def _watermark(self) -> int:
        marks = []
        if self.linewatch is not None:
            marks.append(self.linewatch.position)
        if self.use_annotations:
            marks.append(self._pd_mark)
        return min(marks) if marks else 0

    def _release(self) -> list[dict]:
        mark = self._watermark()
        for rec in self.frames.repeats.expire(mark):
            self._push(rec)
        out = []
        while self._heap and self._heap[0][0] < mark:
            out.append(self._finalize(heapq.heappop(self._heap)[-1]))
        return out

    def _finalize(self, rec: dict) -> dict:
        rec["t_ms"] = round(rec["sample"] * 1000 / self.samplerate, 3)
        return rec


def decode_offline(raw: bytes | None, annotation_lines: Iterable[str], samplerate: int, chunk: int = 0, **kwargs) -> list[dict]:
    """Décodage déterministe (tests, rejeu) à partir d'un flux brut et d'annotations enregistrées.

    Avec ``chunk > 0``, simule le direct : le flux brut est découpé en blocs et les
    annotations sont injectées au fil de l'eau, dès que le flux brut a dépassé leur fin.
    """
    dec = Decoder(samplerate, use_raw=raw is not None, **kwargs)
    out: list[dict] = []
    lines = list(annotation_lines)
    if raw is None or chunk <= 0:
        if raw is not None:
            out += dec.feed_raw(raw)
        for line in lines:
            out += dec.feed_annotation(line)
        return out + dec.finish()
    ends = []
    for line in lines:
        ev = parse_line(line)
        ends.append(ev.end if ev is not None else -1)
    i = 0
    for pos in range(0, len(raw), chunk):
        out += dec.feed_raw(raw[pos:pos + chunk])
        while i < len(lines) and ends[i] < pos + chunk:
            out += dec.feed_annotation(lines[i])
            i += 1
    while i < len(lines):
        out += dec.feed_annotation(lines[i])
        i += 1
    return out + dec.finish()


# -- sigrok --------------------------------------------------------------

def sigrok_bin() -> str:
    path = shutil.which("sigrok-cli")
    if not path:
        raise RuntimeError("sigrok-cli introuvable : installer les paquets sigrok-cli et sigrok-firmware-fx2lafw")
    return path


def pd_command(samplerate: int, scl: int, sda: int, numchannels: int = 8) -> list[str]:
    """Décodeur I2C de sigrok lisant un flux brut sur l'entrée standard (lecture seule)."""
    return [
        sigrok_bin(), "-I", f"binary:numchannels={numchannels}:samplerate={samplerate}", "-i", "-",
        "-P", f"i2c:scl={scl}:sda={sda}", "-A", f"i2c={I2C_CLASSES}", "--protocol-decoder-samplenum",
    ]


def run_stream(
    raw_chunks: Iterator[bytes],
    decoder: Decoder,
    pd_cmd: list[str],
    emit: Callable[[dict], None],
    side_messages: "queue.Queue[str] | None" = None,
    idle_seconds: float | None = None,
) -> None:
    """``idle_seconds`` (direct uniquement) : si sigrok n'a rien produit depuis ce délai,
    le bus est au repos et les événements du flux brut peuvent être publiés."""
    """Alimente en parallèle le détecteur de lignes et le décodeur I2C de sigrok."""
    pd = subprocess.Popen(pd_cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=False)
    lines: "queue.Queue[str | None]" = queue.Queue()

    def reader() -> None:
        assert pd.stdout is not None
        for raw_line in pd.stdout:
            lines.put(raw_line.decode("utf-8", "replace"))
        lines.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()

    last_line = [time.monotonic()]
    written: "list[tuple[float, int]]" = []  # (instant, position) des blocs envoyés à sigrok
    position = 0

    def drain(block: bool = False) -> bool:
        while True:
            try:
                line = lines.get(block=block, timeout=None if block else 0)
            except queue.Empty:
                return True
            if line is None:
                return False
            last_line[0] = time.monotonic()
            for rec in decoder.feed_annotation(line):
                emit(rec)

    assert pd.stdin is not None
    for chunk in raw_chunks:
        for rec in decoder.feed_raw(chunk):
            emit(rec)
        pd.stdin.write(chunk)
        pd.stdin.flush()
        position += len(chunk)
        written.append((time.monotonic(), position))
        drain()
        if side_messages is not None:
            while not side_messages.empty():
                for rec in decoder.note(_side_record(side_messages.get())):
                    emit(rec)
        if idle_seconds is not None and lines.empty():
            now = time.monotonic()
            settled = [pos for t, pos in written if now - t > idle_seconds]
            if settled and now - last_line[0] > idle_seconds:
                for rec in decoder.mark_annotations_idle(settled[-1]):
                    emit(rec)
                written[:] = [(t, pos) for t, pos in written if now - t <= idle_seconds]
    pd.stdin.close()
    while drain(block=True):
        pass
    pd.wait()
    for rec in decoder.finish():
        emit(rec)


def _side_record(message: str) -> dict:
    lower = message.lower()
    if "overflow" in lower or "lost" in lower or "dropped" in lower:
        return {"type": "overflow", "message": message.strip(), "summary": "débordement d'acquisition : décodage incomplet sur cette période"}
    return {"type": "acquisition_warning", "message": message.strip(), "summary": message.strip()}
