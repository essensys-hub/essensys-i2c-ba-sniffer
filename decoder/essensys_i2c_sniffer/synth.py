"""Générateur de signaux I2C synthétiques (corpus et tests uniquement).

Produit des échantillons au format ``sigrok -O binary`` : bit 0 = SCL, bit 1 = SDA.
Ce module ne pilote aucun matériel ; il fabrique des fichiers.
"""

from __future__ import annotations

from .crc import crc16_le


class Waveform:
    def __init__(self, samplerate: int = 1_000_000, bus_hz: int = 50_000) -> None:
        self.samplerate = samplerate
        self.spb = samplerate // bus_hz  # échantillons par bit
        self.data = bytearray()

    def _put(self, scl: int, sda: int, n: int) -> None:
        self.data.extend(bytes([(scl & 1) | ((sda & 1) << 1)]) * max(n, 1))

    def idle_ms(self, ms: float) -> "Waveform":
        self._put(1, 1, int(self.samplerate * ms / 1000))
        return self

    def low(self, line: str, ms: float) -> "Waveform":
        n = int(self.samplerate * ms / 1000)
        self._put(0 if line == "SCL" else 1, 0 if line == "SDA" else 1, n)
        return self

    def start(self) -> None:
        q = self.spb // 4
        self._put(1, 1, q); self._put(1, 0, q); self._put(0, 0, q)

    def rstart(self) -> None:
        q = self.spb // 4
        self._put(0, 1, q); self._put(1, 1, q); self._put(1, 0, q); self._put(0, 0, q)

    def stop(self) -> None:
        q = self.spb // 4
        self._put(0, 0, q); self._put(1, 0, q); self._put(1, 1, q)

    def bit(self, b: int) -> None:
        q = self.spb // 4
        self._put(0, b, q); self._put(1, b, 2 * q); self._put(0, b, q)

    def byte(self, value: int, ack: bool) -> None:
        for i in range(7, -1, -1):
            self.bit((value >> i) & 1)
        self.bit(0 if ack else 1)

    # -- transactions Essensys ---------------------------------------
    def address_nack(self, addr: int) -> "Waveform":
        self.start(); self.byte(addr << 1, False); self.stop()
        return self

    def exchange(self, addr: int, request: bytes, response: bytes | None) -> "Waveform":
        self.start(); self.byte(addr << 1, True)
        for b in request:
            self.byte(b, True)
        if response is not None:
            self.rstart(); self.byte((addr << 1) | 1, True)
            for i, b in enumerate(response):
                self.byte(b, i < len(response) - 1)  # le maître NACK le dernier octet lu
        self.stop()
        return self


def request(code: int, payload: bytes, corrupt_crc: bool = False) -> bytes:
    body = bytes([code]) + payload
    crc = bytearray(crc16_le(body))
    if corrupt_crc:
        crc[0] ^= 0xFF
    return body + bytes(crc)


def response(code: int, req: bytes, accepted: bool = True) -> bytes:
    """Réponse du BA : écho du code, écho du CRC (``00 00`` si rejeté), CRC des 3 octets."""
    echo = req[-2:] if accepted else b"\x00\x00"
    head = bytes([code]) + echo
    return head + crc16_le(head)
