import json
import re
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
