"""Offline image planning: reject ambiguous/destructive intent before hardware."""
import json

import pytest

from essensys_pico.ba_plan import BaPlanError, prepare_ba
from essensys_pico.hex_image import PicImage, HexError


SHA = "0123456789abcdef" * 4


def image(extra=None):
    words = {0: 0xF234, 0x1FFF: 0x0007, 0x2007: 0xFFF2}
    words.update(extra or {})
    return PicImage(words, SHA)


def test_sparse_program_dense_and_private_report():
    result = prepare_ba(image())
    assert len(result.program_words) == 8192
    assert result.program_words[0] == 0x3234
    assert result.program_words[1:0x1FFF] == (0x3FFF,) * 8190
    assert result.program_words[-1] == 7
    assert result.config == 0x3FF2
    assert result.eeprom_policy == "preserve" and result.eeprom is None
    report = result.report()
    assert report["program"] == {
        "strategy": "full-program-rewrite", "words": 8192, "source_words": 2,
        "filled_words": 8190, "fill_word": "0x3FFF",
    }
    assert report["hardware_programming_authorized"] is False
    assert report["verified_backup_required"] is True
    assert report["source_sha256"] == SHA
    assert "program_words" not in json.dumps(report)
    assert "eeprom_snapshot" not in json.dumps(report)


@pytest.mark.parametrize("address", [-1, 0x2004, 0x2005, 0x2006, 0x2008, 0x2009, 0x2010, 0x2200])
def test_reject_reserved_or_calibration_even_for_direct_pic_image(address):
    with pytest.raises(BaPlanError, match="réservée"):
        prepare_ba(image({address: 0x1234}))


@pytest.mark.parametrize("word", [-1, 0x10000, 1.5, True, "0x1234"])
def test_reject_invalid_raw_word(word):
    with pytest.raises(BaPlanError, match="invalide"):
        prepare_ba(image({1: word}))


@pytest.mark.parametrize("config", [0x1FF2, 0x3FB2, 0x3F72, 0x3F32])
def test_config_reserved_bit_and_protections(config):
    with pytest.raises(BaPlanError):
        prepare_ba(image({0x2007: config}))


def test_missing_config_and_program_and_digest():
    with pytest.raises(BaPlanError, match="CONFIG"):
        prepare_ba(PicImage({0: 1}, SHA))
    with pytest.raises(BaPlanError, match="programme"):
        prepare_ba(PicImage({0x2007: 0x3FF2}, SHA))
    with pytest.raises(BaPlanError, match="SHA256"):
        prepare_ba(PicImage({0: 1, 0x2007: 0x3FF2}, "untrusted/path.hex"))


def test_eeprom_payload_requires_explicit_choice():
    source = image({0x2100: 0xFF42})
    with pytest.raises(BaPlanError, match="explicitement"):
        prepare_ba(source)
    preserved = prepare_ba(source, "preserve")
    assert preserved.eeprom is None
    assert preserved.report()["eeprom"] == {
        "policy": "preserve", "source_bytes": 1, "write_bytes": 0,
        "source_ignored_by_explicit_preserve": True,
    }
    with pytest.raises(BaPlanError, match="256"):
        prepare_ba(source, "replace")
    with pytest.raises(BaPlanError, match="256"):
        prepare_ba(image(), "replace")
    with pytest.raises(BaPlanError, match="politique"):
        prepare_ba(image(), "auto")


def test_complete_eeprom_replace_and_missing_last_byte():
    data = {0x2100 + i: (0xFF00 if i & 1 else 0) | (i ^ 0xA5) for i in range(256)}
    result = prepare_ba(image(data), "replace")
    assert result.eeprom == bytes(i ^ 0xA5 for i in range(256))
    assert result.report()["eeprom"]["write_bytes"] == 256
    assert not result.report()["eeprom"]["source_ignored_by_explicit_preserve"]
    del data[0x21FF]
    with pytest.raises(BaPlanError, match="256"):
        prepare_ba(image(data), "replace")
    with pytest.raises(BaPlanError, match="octet haut"):
        prepare_ba(image({0x2100: 0x0142}), "preserve")


def test_user_ids_require_current_matching_values():
    source = image({0x2000: 0xFFFF, 0x2003: 0xF123})
    with pytest.raises(BaPlanError, match="actuel requis"):
        prepare_ba(source)
    with pytest.raises(BaPlanError, match="actuel requis"):
        prepare_ba(source, current_user_ids={0x2000: 0x3FFF})
    with pytest.raises(BaPlanError, match="modification"):
        prepare_ba(source, current_user_ids={0x2000: 0x3FFF, 0x2003: 0x3122})
    result = prepare_ba(source, current_user_ids={0x2000: 0x3FFF, 0x2003: 0x3123})
    assert result.matched_user_id_words == 2
    assert result.report()["user_ids"] == {
        "policy": "preserve-matching-only", "matched_source_words": 2,
    }
    assert "3123" not in json.dumps(result.report())


@pytest.mark.parametrize("current", [{0x2004: 1}, {0x2000: -1}, {0x2000: 0xFFFF}, [1, 2, 3, 4]])
def test_invalid_current_user_ids(current):
    with pytest.raises(BaPlanError):
        prepare_ba(image(), current_user_ids=current)


def test_intel_hex_validation_precedes_preparation(tmp_path):
    # Independent literals: four bytes little-endian at 0000 and CONFIG at 400E.
    file = tmp_path / "source.hex"
    file.write_text(":0400000034127856E8\n:02400E00F2FFBF\n:00000001FF\n")
    parsed = PicImage.read(file)
    plan = prepare_ba(parsed)
    assert plan.program_words[:3] == (0x1234, 0x1678, 0x3FFF)
    assert plan.config == 0x3FF2
    before = file.read_bytes()
    assert len(list(tmp_path.iterdir())) == 1
    assert file.read_bytes() == before
    file.write_text(":0400000034127856E9\n:02400E00F2FFBF\n:00000001FF\n")
    with pytest.raises(HexError, match="checksum"):
        prepare_ba(PicImage.read(file))
