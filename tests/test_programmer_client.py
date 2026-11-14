import io
import json

import pytest

from essensys_pico import cli
from essensys_pico.programmer import diagnostic_request
from essensys_pico.transport import ProtocolError


class Port:
    def __init__(self, wire):
        self.input = io.BytesIO(wire)
        self.sent = bytearray()

    def write(self, data):
        self.sent.extend(data)
        return len(data)

    def read(self, count):
        return self.input.read(count)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def header(command="INFO"):
    common = {"schema": "essensys.programmer.v1", "status": "ok", "target": "none",
              "programming_enabled": False}
    if command == "INFO":
        return {**common, "kind": "info", "mode": "diagnostic-only", "hardware_qualified": False,
                "ports": ["bp-bdm", "ba-icsp"], "capture": "fx2"}
    if command == "STATUS":
        return {**common, "kind": "state", "outputs_commanded_safe": True, "rails_measured": False}
    return {**common, "kind": "stopped"}


def encode(data):
    return (json.dumps(data) + "\n").encode()


@pytest.mark.parametrize("command", ["INFO", "STATUS", "STOP"])
def test_diagnostic_and_cli_roundtrip(command, monkeypatch, capsys):
    port = Port(encode(header(command)))
    monkeypatch.setattr(cli, "open_port", lambda *args: port)
    assert cli.main(["programmer-" + command.lower(), "--port", "synthetic"]) == 0
    assert port.sent == (command + "\n").encode()
    assert json.loads(capsys.readouterr().out)["programming_enabled"] is False


@pytest.mark.parametrize("patch", [{"schema": "essensys.pico.v1"}, {"kind": "stopped"},
    {"target": "bp"}, {"hardware_qualified": 0}, {"programming_enabled": "false"},
    {"ports": ["ba-icsp"]}, {"capture": "pio"}, {"status": "error", "error": "fault"}])
def test_incompatible_or_incoherent_firmware_rejected(patch):
    with pytest.raises(ProtocolError):
        diagnostic_request(Port(encode({**header(), **patch})), "INFO")


@pytest.mark.parametrize("wire", [b"", b"{}", b"[]\n", b"x\n", b"x" * 512 + b"\n",
    b'{"status":"ok","status":"error"}\n', b'{"value":NaN}\n'])
def test_bad_json_and_truncation_rejected(wire):
    with pytest.raises(ProtocolError):
        diagnostic_request(Port(wire), "INFO")


def test_unrecognized_command_never_written():
    port = Port(b"")
    with pytest.raises(ValueError):
        diagnostic_request(port, "PROGRAM")
    assert not port.sent


def test_short_write_and_global_deadline():
    port = Port(encode(header()))
    port.write = lambda data: len(data) - 1
    with pytest.raises(ProtocolError, match="incomplète"):
        diagnostic_request(port, "INFO")
    ticks = iter([0, 1, 2, 3, 4, 5])
    with pytest.raises(ProtocolError, match="délai"):
        diagnostic_request(Port(encode(header())), "INFO", clock=lambda: next(ticks))


def test_ba_plan_cli_never_opens_usb(monkeypatch, capsys):
    from essensys_pico.hex_image import PicImage
    source = PicImage({0: 0x1234, 0x2007: 0xFFF2, 0x2100: 0xFF42}, "a" * 64)
    monkeypatch.setattr(cli.PicImage, "read", lambda path: source)
    def forbidden(*args):
        pytest.fail("offline plan opened a USB port")
    monkeypatch.setattr(cli, "open_port", forbidden)
    assert cli.main(["plan-ba", "synthetic.hex"]) == 2
    assert "explicitement" in capsys.readouterr().err
    assert cli.main(["plan-ba", "synthetic.hex", "--eeprom", "preserve"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["hardware_programming_authorized"] is False
    assert report["program"]["filled_words"] == 8191
