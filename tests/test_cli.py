import json
import re
import subprocess
from pathlib import Path

import pytest

from conftest import CORPUS, needs_sigrok
from essensys_i2c_sniffer import SCHEMA, cli

PKG = Path(cli.__file__).parent


def test_nr_i2c_ba_sniffer_1_aucune_commande_d_emission_ou_d_injection_exposee():
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    assert set(sub.choices) == {"live", "replay", "annotations", "correlate"}
    forbidden = re.compile(r"/dev/i2c|smbus|SMBus|import socket|urllib|requests|http\.client|admin/inject|api/myactions|--config.*trigger|-O\s+\"?srzip", re.I)
    for source in PKG.glob("*.py"):
        text = source.read_text()
        for line in text.splitlines():
            if line.strip().startswith(("#", '"', "'")) or "inject" in line and "aucune" in line.lower():
                continue
            assert not forbidden.search(line), f"{source.name}: {line.strip()}"


def test_live_acquisition_is_read_only(monkeypatch):
    seen = {}

    class Stop(Exception):
        pass

    def fake_popen(cmd, **kwargs):
        seen["cmd"] = cmd
        raise Stop

    monkeypatch.setattr(cli, "sigrok_bin", lambda: "sigrok-cli")
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)
    with pytest.raises(Stop):
        cli.main(["live", "--duration", "1"])
    cmd = seen["cmd"]
    assert cmd[:3] == ["sigrok-cli", "-d", "fx2lafw"] and "-O" in cmd and cmd[cmd.index("-O") + 1] == "binary"
    assert cmd[cmd.index("--channels") + 1] == "D0,D1,D2,D3,D4,D5,D6,D7"


@pytest.mark.parametrize("options", [["--driver", "demo:num_logic_channels=16"],
    ["--scl", "8"], ["--sda", "-1"], ["--scl", "1", "--sda", "1"]])
def test_live_rejects_unknown_width_before_acquisition(monkeypatch, options):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid acquisition started")
    monkeypatch.setattr(cli.subprocess, "Popen", forbidden)
    with pytest.raises(SystemExit):
        cli.main(["live", *options])


@needs_sigrok
def test_replay_refuses_real_sigrok_16bit_stream(tmp_path):
    path = tmp_path / "wide.sr"
    subprocess.run([cli.sigrok_bin(), "-d", "demo:logic_channels=16:analog_channels=0",
                    "--samples", "32", "--config", "samplerate=1000000",
                    "-O", "srzip", "-o", str(path)], check=True, capture_output=True)
    raw = subprocess.run([cli.sigrok_bin(), "-i", str(path), "-O", "binary"],
                         check=True, capture_output=True).stdout
    assert len(raw) == 64
    with pytest.raises(SystemExit, match="unitsize 1"):
        cli.main(["replay", str(path)])


@pytest.mark.parametrize("width", [2, "1", True])
def test_raw_metadata_width_is_not_silently_reinterpreted(tmp_path, width):
    path = tmp_path / "raw.bin"
    path.write_bytes(b"\x01\x00" * 8)
    Path(str(path) + ".json").write_text(json.dumps({"samplerate": 1000000, "unitsize": width}))
    with pytest.raises(SystemExit, match="unitsize 1"):
        cli.main(["replay", str(path)])


@pytest.mark.parametrize("rate", ["500k", "999999"])
def test_samplerate_below_1mhz_refused(rate):
    with pytest.raises(SystemExit) as exc:
        cli.main(["annotations", str(CORPUS / "address_nack.ann.txt"), "--samplerate", rate])
    assert "1000000" in str(exc.value)


def test_ndjson_output_is_versioned(capsys):
    cli.main(["annotations", str(CORPUS / "cas_installation_2026_10.ann.txt"), "--samplerate", "1m", "--format", "ndjson"])
    lines = capsys.readouterr().out.splitlines()
    records = [json.loads(l) for l in lines]
    assert records[0]["type"] == "session"
    assert all(r["schema"] == SCHEMA for r in records)


def test_text_output_readable(capsys):
    cli.main(["annotations", str(CORPUS / "cas_installation_2026_10.ann.txt"), "--samplerate", "1m"])
    out = capsys.readouterr().out
    assert "0x12 chambres — NACK d'adresse — BA absent" in out
    assert "trame reçue et validée CRC par le BA" in out


@needs_sigrok
def test_replay_gz_matches_expected(capsys, tmp_path):
    cli.main(["replay", str(CORPUS / "cas_installation_2026_10.bin.gz"), "--samplerate", "1m", "--format", "ndjson"])
    got = [json.loads(l) for l in capsys.readouterr().out.splitlines()][1:]
    expected = [json.loads(l) for l in (CORPUS / "cas_installation_2026_10.expected.ndjson").read_text().splitlines()]
    assert got == [{"schema": SCHEMA, **{k: v for k, v in r.items() if k != "schema"}} for r in expected]
