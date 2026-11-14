"""Protocole USB CDC : une ligne JSON bornée, suivie d'un bloc de capture."""

from __future__ import annotations

import json
import zlib

MAX_SAMPLES = 262144
SCHEMA = "essensys.pico.v1"


class ProtocolError(ValueError):
    pass


def read_header(port) -> dict:
    data = bytearray()
    while len(data) < 512:
        byte = port.read(1)
        if not byte:
            raise ProtocolError("réponse absente ou en-tête tronqué")
        data.extend(byte)
        if byte == b"\n":
            break
    else:
        raise ProtocolError("en-tête trop long")
    try:
        header = json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ProtocolError("en-tête JSON invalide") from exc
    if not isinstance(header, dict) or header.get("schema") != SCHEMA:
        raise ProtocolError("version de protocole inconnue")
    if header.get("status") != "ok":
        raise ProtocolError(f"Pico : {header.get('error', 'échec non précisé')}")
    return header


def validate_request(rate: int, count: int) -> None:
    if type(rate) is not int or not 1000 <= rate <= 10_000_000:
        raise ValueError("fréquence hors plage 1 kHz..10 MHz (limite logicielle)")
    if type(count) is not int or not 4 <= count <= MAX_SAMPLES or count % 4:
        raise ValueError("échantillons : multiple de 4 entre 4 et 262144")


def capture(port, rate: int, count: int) -> tuple[bytes, dict]:
    validate_request(rate, count)
    command = f"CAPTURE {rate} {count}\n".encode("ascii")
    if port.write(command) != len(command):
        raise ProtocolError("commande USB incomplète")
    header = read_header(port)
    expected = {"kind": "capture", "channels": 8, "samplerate": rate, "samples": count}
    if any(type(header.get(k)) is not type(v) or header[k] != v for k, v in expected.items()):
        raise ProtocolError("paramètres de capture reçus incohérents")
    checksum = header.get("crc32")
    if type(checksum) is not int or not 0 <= checksum <= 0xFFFFFFFF:
        raise ProtocolError("CRC32 absent ou invalide")
    payload = bytearray()
    while len(payload) < count:
        block = port.read(min(4096, count - len(payload)))
        if not block:
            raise ProtocolError(f"capture tronquée : {len(payload)}/{count} échantillons")
        payload.extend(block)
    if zlib.crc32(payload) != checksum:
        raise ProtocolError("capture corrompue : CRC32 incorrect")
    return bytes(payload), header
