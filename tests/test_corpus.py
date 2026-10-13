"""Non-régression sur le corpus de référence (sans matériel ni armoire)."""

import json
import subprocess

import pytest

from conftest import CORPUS, RATE, load, needs_sigrok
from essensys_i2c_sniffer.output import to_ndjson
from essensys_i2c_sniffer.pipeline import I2C_CLASSES, decode_offline, sigrok_bin

NAMES = sorted(p.name[: -len(".expected.ndjson")] for p in CORPUS.glob("*.expected.ndjson"))


def render(records):
    return [to_ndjson(r) for r in records]


def test_corpus_covers_required_cases():
    required = {"forcage_sorties_ok", "conf_sorties_ok", "tps_extinction_ok", "tps_action_ok", "actions_ok",
                "address_nack", "crc_faux", "repetitions_abandon", "ligne_bloquee"}
    assert required <= set(NAMES)


@pytest.mark.parametrize("name", NAMES)
def test_corpus_decoding_matches_expected(name):
    raw, ann, expected = load(name)
    assert render(decode_offline(raw, ann, RATE)) == expected


@pytest.mark.parametrize("name", NAMES)
def test_nr_i2c_ba_sniffer_6_rejeu_identique_au_direct_sur_le_corpus(name):
    raw, ann, expected = load(name)
    for chunk in (4096, 65536, 1_000_003):
        assert render(decode_offline(raw, ann, RATE, chunk=chunk)) == expected


def test_nr_i2c_ba_sniffer_2_nack_d_adresse_qualifie_ba_absent_corpus():
    _, _, expected = load("address_nack")
    rec = json.loads(expected[0])
    assert rec["kind"] == "address_nack" and rec["addr"] == "0x12" and rec["nack_count"] == 1


def test_nr_i2c_ba_sniffer_5_ligne_sda_ou_scl_bloquee_detectee():
    _, _, expected = load("ligne_bloquee")
    stuck = [json.loads(l) for l in expected if '"line_stuck"' in l]
    assert stuck and stuck[0]["line"] == "SDA" and stuck[0]["duration_ms"] >= 10


def test_installation_case_shows_only_pdv_answering():
    _, _, expected = load("cas_installation_2026_10")
    recs = [json.loads(l) for l in expected]
    status = {r["addr"]: r["status"] for r in recs if r["type"] == "exchange"}
    assert status == {"0x11": "validated", "0x12": "absent", "0x13": "absent"}


@needs_sigrok
@pytest.mark.parametrize("name", NAMES)
def test_sigrok_oracle_reproduces_annotations(name):
    raw, ann, _ = load(name)
    cmd = [sigrok_bin(), "-I", f"binary:numchannels=2:samplerate={RATE}", "-i", "-", "-P", "i2c:scl=0:sda=1",
           "-A", f"i2c={I2C_CLASSES}", "--protocol-decoder-samplenum"]
    out = subprocess.run(cmd, input=raw, capture_output=True, check=True).stdout.decode().splitlines()
    assert out == ann
