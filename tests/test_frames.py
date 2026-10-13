from essensys_i2c_sniffer.frames import FrameDecoder, decode_transaction
from essensys_i2c_sniffer.synth import request, response
from essensys_i2c_sniffer.transactions import Phase, Transaction


def exchange(addr, req, resp, addr_ack=True):
    phases = [Phase("W", addr, addr_ack, list(req), [True] * len(req))]
    if resp is not None:
        phases.append(Phase("R", addr, True, list(resp), [True] * (len(resp) - 1) + [False]))
    return Transaction(start=100, end=200, phases=phases, stopped=True)


def test_validated_exchange():
    req = request(1, bytes(8))
    rec = decode_transaction(exchange(0x11, req, response(1, req)))
    assert rec["status"] == "validated" and rec["frame"]["length_ok"] and rec["frame"]["crc"]["ok"]
    assert rec["summary"] == "trame reçue et validée CRC par le BA"


def test_length_checked_per_code():
    rec = decode_transaction(exchange(0x11, request(3, bytes(8)), None))
    assert not rec["frame"]["length_ok"]
    assert "commands" not in rec  # pas d'interprétation sémantique
    assert any("longueur" in a for a in rec["anomalies"])


def test_unknown_code_flagged():
    rec = decode_transaction(exchange(0x11, request(9, bytes(2)), None))
    assert rec["frame"]["name"] == "INCONNU"
    assert any("code de trame inconnu" in a for a in rec["anomalies"])


def test_nr_i2c_ba_sniffer_3_crc_de_requete_faux_signale():
    bad = request(1, bytes(8), corrupt_crc=True)
    rec = decode_transaction(exchange(0x11, bad, response(1, bad, accepted=False)))
    assert rec["frame"]["crc"]["ok"] is False
    assert rec["status"] == "rejected" and "écho CRC 0x0000" in rec["summary"]


def test_nr_i2c_ba_sniffer_2_nack_d_adresse_qualifie_ba_absent():
    rec = decode_transaction(Transaction(start=1, end=2, phases=[Phase("W", 0x12, False)], stopped=True))
    assert rec["kind"] == "address_nack" and rec["status"] == "absent"
    assert rec["ba_name"] == "chambres" and rec["addr"] == "0x12"


def test_response_never_claims_physical_switching():
    req = request(1, bytes([0, 1, 0, 0, 0, 0, 0, 0]))
    rec = decode_transaction(exchange(0x11, req, response(1, req)))
    assert "commut" not in rec["summary"]


def test_unknown_address_kept_raw():
    req = request(5, bytes(1))
    rec = decode_transaction(exchange(0x20, req, response(5, req)))
    assert rec["addr"] == "0x20" and rec["ba"] is None
    assert any("hors plage" in a for a in rec["anomalies"])


def test_nr_i2c_ba_sniffer_4_repetitions_puis_abandon_detectes():
    dec = FrameDecoder(samplerate=1000, repeat_window_s=1.0)
    out = []
    for s in (0, 100, 200):
        out += dec.feed(Transaction(start=s, end=s + 1, phases=[Phase("W", 0x13, False)], stopped=True))
    out += dec.flush(5000)
    exchanges = [r for r in out if r["type"] == "exchange"]
    assert [r.get("repeat", {}).get("rank", 0) for r in exchanges] == [0, 1, 2]
    abandon = [r for r in out if r["type"] == "abandon"]
    assert len(abandon) == 1 and abandon[0]["attempts"] == 3


def test_validated_exchange_clears_pending():
    dec = FrameDecoder(samplerate=1000, repeat_window_s=1.0)
    req = request(1, bytes(8))
    dec.feed(exchange(0x11, req, response(1, req, accepted=False)))
    dec.feed(Transaction(start=300, end=301, phases=exchange(0x11, req, response(1, req)).phases, stopped=True))
    assert dec.flush(10_000) == []
