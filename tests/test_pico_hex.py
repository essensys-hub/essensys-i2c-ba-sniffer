"""NR-pico2-hex : refuser les images ambiguës avant tout accès matériel."""

from pathlib import Path

import pytest

from essensys_pico.hex_image import HexError, PicImage, parse_records


def record(address, payload=b"", kind=0):
    data = bytes([len(payload), address >> 8, address & 255, kind]) + payload
    return ":" + (data + bytes([-sum(data) & 255])).hex().upper()


def image_file(tmp_path: Path, config=b"\xf2\xff", extra=()):
    lines = [record(0, b"\x00\x00\xff\x3f"), record(0x400E, config), *extra, record(0, kind=1)]
    path = tmp_path / "fixture.hex"
    path.write_text("\n".join(lines) + "\n")
    return path


def test_historical_config_normalized_with_no_lvp(tmp_path):
    report = PicImage.read(image_file(tmp_path)).report()
    assert report["config_raw"] == "0xFFF2"
    assert report["config_14bit"] == "0x3FF2"
    assert report["config"] == {"FOSC": 2, "MCLRE": 1, "CP": 1, "CPD": 1}
    assert report["entry"] == "VDD-first-compatible"
    assert not report["lvp_supported"]
    assert not report["hardware_programming_authorized"]


def test_internal_clock_without_mclr_requires_vpp_first(tmp_path):
    report = PicImage.read(image_file(tmp_path, b"\xc4\x3f")).report()
    assert report["entry"] == "VPP-first-required"


@pytest.mark.parametrize("records", [
    [":020000000000FF", record(0, kind=1)],
    [record(0, b"\x01"), record(0, b"\x01"), record(0, kind=1)],
    [record(0, b"\x01")],
    [record(0, kind=1), record(0, b"\x01")],
    [record(0, b"\x00\x01", 4), record(0, b"\x00\x00"), record(0, kind=1)],
    [record(0xFFFF, b"\x00\x00"), record(0, kind=1)],
    [record(0, b"\x00", 1)],
])
def test_bad_records_rejected(records):
    with pytest.raises(HexError):
        parse_records("\n".join(records))


@pytest.mark.parametrize("address", [0x4008, 0x400C, 0x4010, 0x4012, 0x4100])
def test_reserved_id_and_calibration_never_writable(tmp_path, address):
    with pytest.raises(HexError, match="réservée"):
        PicImage.read(image_file(tmp_path, extra=[record(address, b"\x00\x00")]))


@pytest.mark.parametrize("config", [b"\xf2", b""])
def test_missing_or_partial_config_rejected(tmp_path, config):
    with pytest.raises(HexError):
        PicImage.read(image_file(tmp_path, config))


def test_eeprom_count_and_extended_segment(tmp_path):
    path = image_file(tmp_path, extra=[record(0, b"\x04\x20", 2), record(0, b"\x42\x00")])
    assert PicImage.read(path).report()["eeprom_bytes"] == 1
