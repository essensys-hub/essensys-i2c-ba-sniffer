"""Préparation pure d'une image BA PIC16F946 pour le moteur ICSP.

Pas de périphérique, d'écriture de fichier ou d'autorisation de programmation.
Le HEX reste chargé/validé par PicImage ; les invariants sont revérifiés ici pour
refuser aussi un objet PicImage construit directement avec une image invalide.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re

from .hex_image import PicImage

PROGRAM_WORDS = 8192
EEPROM_BYTES = 256
USER_ID_ADDRESSES = frozenset(range(0x2000, 0x2004))


class BaPlanError(ValueError):
    """Préparation refusée avant tout accès matériel."""


@dataclass(frozen=True)
class BaPlan:
    program_words: tuple[int, ...]
    config: int
    eeprom_policy: str
    eeprom: bytes | None
    source_sha256: str
    source_program_words: int
    source_eeprom_bytes: int
    matched_user_id_words: int

    def report(self) -> dict:
        """Résumé JSON sans contenu firmware, EEPROM, identifiants ni chemin."""
        return {
            "schema": "essensys.pic16f946.plan.v1",
            "device": "PIC16F946",
            "source_sha256": self.source_sha256,
            "program": {
                "strategy": "full-program-rewrite",
                "words": len(self.program_words),
                "source_words": self.source_program_words,
                "filled_words": len(self.program_words) - self.source_program_words,
                "fill_word": "0x3FFF",
            },
            "config_14bit": f"0x{self.config:04X}",
            "eeprom": {
                "policy": self.eeprom_policy,
                "source_bytes": self.source_eeprom_bytes,
                "write_bytes": len(self.eeprom) if self.eeprom is not None else 0,
                "source_ignored_by_explicit_preserve": (
                    self.source_eeprom_bytes > 0 and self.eeprom_policy == "preserve"
                ),
            },
            "user_ids": {
                "policy": "preserve-matching-only",
                "matched_source_words": self.matched_user_id_words,
            },
            "calibration_policy": "never-write",
            "verified_backup_required": True,
            "hardware_qualification_required": True,
            "hardware_programming_authorized": False,
        }


def _integer(value: object) -> bool:
    # bool is an int subclass, but never a valid explicit address/data word.
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_image(image: PicImage) -> dict[int, int]:
    if not isinstance(image, PicImage):
        raise BaPlanError("une image PicImage validée est requise")
    if not isinstance(image.sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", image.sha256):
        raise BaPlanError("empreinte SHA256 source invalide")
    if not isinstance(image.raw_words, Mapping):
        raise BaPlanError("table des mots PIC invalide")
    normalized: dict[int, int] = {}
    for address, raw in image.raw_words.items():
        if not _integer(address) or not _integer(raw) or not 0 <= raw <= 0xFFFF:
            raise BaPlanError("adresse ou mot PIC invalide")
        permitted = (0 <= address < PROGRAM_WORDS or address in USER_ID_ADDRESSES
                     or address == 0x2007 or 0x2100 <= address <= 0x21FF)
        if not permitted:
            raise BaPlanError(f"zone réservée, identité ou calibration à 0x{address:X}")
        if 0x2100 <= address <= 0x21FF:
            if raw >> 8 not in (0, 255):
                raise BaPlanError(f"octet haut EEPROM invalide à 0x{address:04X}")
            normalized[address] = raw & 0xFF
        else:
            # Intel HEX may store unimplemented top bits as 0 or 1 (e.g. FFF2).
            # Only normalize after the raw 16-bit word and address are validated.
            normalized[address] = raw & 0x3FFF
    if 0x2007 not in normalized:
        raise BaPlanError("mot CONFIG 0x2007 absent")
    if not any(address < PROGRAM_WORDS for address in normalized):
        raise BaPlanError("aucun mot de programme")
    return normalized


def _validate_current_ids(current_user_ids: Mapping[int, int] | None) -> dict[int, int]:
    if current_user_ids is None:
        return {}
    if not isinstance(current_user_ids, Mapping):
        raise BaPlanError("identifiants actuels attendus sous forme de mapping adresse/valeur")
    validated = {}
    for address, word in current_user_ids.items():
        if (not _integer(address) or address not in USER_ID_ADDRESSES
                or not _integer(word) or not 0 <= word <= 0x3FFF):
            raise BaPlanError("identifiant actuel invalide : adresse 2000..2003 et mot 14 bits requis")
        validated[address] = word
    return validated


def prepare_ba(
    image: PicImage,
    eeprom_policy: str | None = None,
    current_user_ids: Mapping[int, int] | None = None,
) -> BaPlan:
    """Prepare a full program rewrite without selecting or opening any hardware.

    EEPROM absent: preserve by default. EEPROM present: explicitly choose
    preserve (reported as intentionally ignored) or replace (requires 256 bytes).
    Requested user-ID words must equal provided current 14-bit values. They are
    preserved by the engine; this planner never silently drops ID modifications.
    """
    words = _validate_image(image)
    config = words[0x2007]
    if not config & 0x2000:
        raise BaPlanError("CONFIG invalide : bit 13 non implémenté attendu à 1")
    if config & 0xC0 != 0xC0:
        raise BaPlanError("image refusée : CP et CPD doivent rester à 1 pour la vérification")
    # Entry profile/actual target configuration are hardware-session decisions.
    # MCLRE=0 may only be used by a qualified VPP-first, VDD-switchable adapter.
    current_ids = _validate_current_ids(current_user_ids)
    requested_ids = {a: words[a] for a in USER_ID_ADDRESSES if a in words}
    for address, wanted in requested_ids.items():
        if address not in current_ids:
            raise BaPlanError(f"identifiant actuel requis pour préserver 0x{address:04X}")
        if current_ids[address] != wanted:
            raise BaPlanError(f"modification d'identifiant non prise en charge à 0x{address:04X}")
    eeprom_words = {a: word for a, word in words.items() if 0x2100 <= a <= 0x21FF}
    if eeprom_policy not in (None, "preserve", "replace"):
        raise BaPlanError("politique EEPROM attendue : preserve ou replace")
    if eeprom_words and eeprom_policy is None:
        raise BaPlanError("le HEX contient de l'EEPROM : choisir explicitement preserve ou replace")
    selected_policy = eeprom_policy or "preserve"
    eeprom = None
    if selected_policy == "replace":
        if len(eeprom_words) != EEPROM_BYTES:
            raise BaPlanError("le remplacement EEPROM exige les 256 octets, sans trou")
        eeprom = bytes(eeprom_words[address] for address in range(0x2100, 0x2200))
    program = tuple(words.get(address, 0x3FFF) for address in range(PROGRAM_WORDS))
    return BaPlan(
        program_words=program,
        config=config,
        eeprom_policy=selected_policy,
        eeprom=eeprom,
        source_sha256=image.sha256.lower(),
        source_program_words=sum(address < PROGRAM_WORDS for address in words),
        source_eeprom_bytes=len(eeprom_words),
        matched_user_id_words=len(requested_ids),
    )
