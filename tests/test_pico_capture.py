import io
import json
import zlib

import pytest

from essensys_pico import cli
from essensys_pico.transport import ProtocolError, capture
from conftest import load, needs_sigrok


class Port:
    def __init__(self, data, **overrides):
        header = {"schema": "essensys.pico.v1", "status": "ok", "kind": "capture",
                  "channels": 8, "samplerate": 1_000_000, "samples": len(data),
                  "crc32": zlib.crc32(data), **overrides}
        self.input = io.BytesIO(json.dumps(header).encode() + b"\n" + data)
        self.written = bytearray()

    def read(self, count):
        return self.input.read(min(count, 7))  # Exercise fragmented CDC reads.

    def write(self, data):
        self.written.extend(data)
        return len(data)


def test_all_eight_channels_and_binary_newlines_preserved(tmp_path):
    data = bytes(range(256))
    port = Port(data)
    received, header = capture(port, 1_000_000, 256)
    assert received == data
    assert port.written == b"CAPTURE 1000000 256\n"
    path = tmp_path / "capture.bin"
    cli.save_capture(path, received, header)
    assert path.read_bytes() == data
    meta = json.loads((tmp_path / "capture.bin.json").read_text())
    assert meta["samplerate"] == 1_000_000
    assert meta["complete"] and (meta["scl"], meta["sda"]) == (0, 1)


@pytest.mark.parametrize("change", [
    {"crc32": 123}, {"samples": 512}, {"samplerate": 500_000},
    {"channels": 2}, {"schema": "unknown"}, {"status": "error"},
    {"crc32": -1}, {"samples": True},
])
def test_inconsistent_frames_refused(change):
    with pytest.raises(ProtocolError):
        capture(Port(bytes(range(256)), **change), 1_000_000, 256)


def test_truncated_payload_refused():
    port = Port(b"abcd", samples=256)
    with pytest.raises(ProtocolError, match="tronquée"):
        capture(port, 1_000_000, 256)


@pytest.mark.parametrize("rate,count", [(0, 4), (24_000_000, 4), (1_000_000, 3), (1_000_000, 262148)])
def test_invalid_request_sends_nothing(rate, count):
    port = Port(b"abcd")
    with pytest.raises(ValueError):
        capture(port, rate, count)
    assert not port.written


def test_existing_capture_not_overwritten(tmp_path):
    path = tmp_path / "capture.bin"
    path.write_bytes(b"reference")
    with pytest.raises(FileExistsError):
        cli.save_capture(path, b"new", {})
    assert path.read_bytes() == b"reference"


def test_inspect_hex_never_opens_port(tmp_path, monkeypatch):
    from test_pico_hex import image_file
    monkeypatch.setattr(cli, "open_port", lambda *args: pytest.fail("inspection must be offline"))
    assert cli.main(["inspect-hex", str(image_file(tmp_path))]) == 0


def test_programming_unavailable_before_qualification():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["program"])


def test_invalid_cli_request_never_opens_port(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "open_port", lambda *args: pytest.fail("invalid request opened USB"))
    assert cli.main(["capture", "--port", "unused", "--samples", "3",
                     "--out", str(tmp_path / "capture.bin")]) == 2


@needs_sigrok
def test_pico_capture_replays_through_existing_decoder(tmp_path, capsys):
    from essensys_i2c_sniffer import SCHEMA, cli as decoder
    raw, _, expected = load("cas_installation_2026_10")
    # Six independently varying upper bits must not affect I2C on bits 0/1.
    payload = bytes((value & 3) | ((i % 64) << 2) for i, value in enumerate(raw))
    payload += bytes([payload[-1]]) * (-len(payload) % 4)
    received, header = capture(Port(payload), 1_000_000, len(payload))
    path = tmp_path / "pico.bin"
    cli.save_capture(path, received, header)
    assert decoder.main(["replay", str(path), "--format", "ndjson"]) == 0
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()][1:]
    assert records == [{**json.loads(line), "schema": SCHEMA} for line in expected]
