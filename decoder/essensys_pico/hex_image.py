"""Lecture stricte Intel HEX pour PIC16F946, sans accès à un périphérique.

Les adresses HEX sont des adresses d'octets : CONFIG 0x2007 devient 0x400E.
Les deux bits supérieurs des mots PIC ne sont pas implémentés. Les images
historiques les stockent notamment à 1 dans CONFIG (0xFFF2 -> 0x3FF2).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class HexError(ValueError):
    """Image refusée : ne doit jamais conduire à une commande matérielle."""


def parse_records(text: str) -> dict[int, int]:
    memory: dict[int, int] = {}
    base, eof = 0, False
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if eof:
            raise HexError(f"ligne {number} : données après EOF")
        if not line.startswith(":"):
            raise HexError(f"ligne {number} : préfixe Intel HEX absent")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as exc:
            raise HexError(f"ligne {number} : octet hexadécimal invalide") from exc
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
            raise HexError(f"ligne {number} : longueur ou checksum invalide")
        size, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
        data = record[4:-1]
        if kind == 0:
            if address + size > 0x10000:
                raise HexError(f"ligne {number} : franchissement de segment")
            for offset, value in enumerate(data):
                location = base + address + offset
                if location in memory:
                    raise HexError(f"ligne {number} : recouvrement à 0x{location:X}")
                if location > 0x43FF:
                    raise HexError(f"ligne {number} : adresse hors PIC16F946")
                memory[location] = value
        elif kind == 1 and size == 0 and address == 0:
            eof = True
        elif kind in (2, 4) and size == 2 and address == 0:
            base = int.from_bytes(data, "big") << (4 if kind == 2 else 16)
        else:
            raise HexError(f"ligne {number} : record {kind} non pris en charge")
    if not eof:
        raise HexError("record EOF absent")
    return memory


@dataclass(frozen=True)
class PicImage:
    raw_words: dict[int, int]
    sha256: str

    @classmethod
    def read(cls, path: Path) -> "PicImage":
        if path.stat().st_size > 2_000_000:
            raise HexError("image trop volumineuse pour un PIC16F946")
        data = path.read_bytes()
        try:
            memory = parse_records(data.decode("ascii"))
        except UnicodeDecodeError as exc:
            raise HexError("Intel HEX doit être ASCII") from exc
        words = {}
        for byte_address in sorted(memory):
            if byte_address & 1:
                if byte_address - 1 not in memory:
                    raise HexError(f"mot incomplet à 0x{byte_address // 2:04X}")
                continue
            if byte_address + 1 not in memory:
                raise HexError(f"mot incomplet à 0x{byte_address // 2:04X}")
            address = byte_address // 2
            allowed = address < 0x2000 or address in range(0x2000, 0x2004)
            allowed |= address == 0x2007 or address in range(0x2100, 0x2200)
            if not allowed:
                raise HexError(f"zone réservée, Device ID ou calibration à 0x{address:04X}")
            word = memory[byte_address] | memory[byte_address + 1] << 8
            if 0x2100 <= address < 0x2200 and word >> 8 not in (0, 255):
                raise HexError(f"octet haut EEPROM invalide à 0x{address:04X}")
            words[address] = word
        if 0x2007 not in words:
            raise HexError("mot CONFIG 0x2007 absent")
        if not any(address < 0x2000 for address in words):
            raise HexError("aucun mot de programme")
        return cls(words, hashlib.sha256(data).hexdigest())

    def report(self) -> dict:
        raw = self.raw_words[0x2007]
        config = raw & 0x3FFF
        internal_clock = (config & 7) in (4, 5)
        vpp_first = internal_clock and not (config & 0x20)
        return {
            "schema": "essensys.pic16f946.hex.v1",
            "sha256": self.sha256,
            "device": "PIC16F946",
            "config_raw": f"0x{raw:04X}",
            "config_14bit": f"0x{config:04X}",
            "config": {"FOSC": config & 7, "MCLRE": (config >> 5) & 1,
                       "CP": (config >> 6) & 1, "CPD": (config >> 7) & 1},
            "lvp_supported": False,
            "vpp_volts": [10, 12],
            "entry": "VPP-first-required" if vpp_first else "VDD-first-compatible",
            "program_words": sum(a < 0x2000 for a in self.raw_words),
            "eeprom_bytes": sum(0x2100 <= a < 0x2200 for a in self.raw_words),
            "calibration_policy": "never-write",
            "hardware_programming_authorized": False,
        }
