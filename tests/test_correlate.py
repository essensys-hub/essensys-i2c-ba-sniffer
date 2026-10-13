from datetime import datetime

from conftest import RATE, load
from essensys_i2c_sniffer.correlate import correlate, parse_backend_log
from essensys_i2c_sniffer.pipeline import decode_offline

# Journal anonymisé (GUID fictifs), au format de « docker logs essensys-backend ».
LOG = """\
2026/10/13 11:22:00 [GO] 13/10/2026 11:22:00 POST /api/admin/inject (<ip-poste>)
2026/10/13 11:22:01 [GO] Sending Actions: {"_de67f":null,"actions":[{"guid":"00000000-0000-0000-0000-000000000001","params":[{"k":590,"v":"1"},{"k":605,"v":"0"},{"k":611,"v":"1"}]}]}
2026/10/13 11:22:01 [GO] Action acknowledged: 00000000-0000-0000-0000-000000000001
2026/10/13 11:22:01 [GO] Sending Actions: {"_de67f":null,"actions":[{"guid":"00000000-0000-0000-0000-000000000002","params":[{"k":590,"v":"1"},{"k":613,"v":"64"}]}]}
2026/10/13 11:22:01 [GO] Action acknowledged: 00000000-0000-0000-0000-000000000002
2026/10/13 11:22:01 [GO] Sending Actions: {"_de67f":null,"actions":[{"guid":"00000000-0000-0000-0000-000000000003","params":[{"k":590,"v":"1"},{"k":615,"v":"64"}]}]}
2026/10/13 11:22:01 [GO] Action acknowledged: 00000000-0000-0000-0000-000000000003
"""


def test_parse_backend_log_targets():
    actions = parse_backend_log(LOG.splitlines())
    assert [sorted(a.targets) for a in actions] == [[0x11], [0x12], [0x13]]
    assert all(a.acked is not None for a in actions)


def test_acknowledged_but_not_received_reported():
    raw, ann, _ = load("cas_installation_2026_10")
    records = decode_offline(raw, ann, RATE)
    results, offset = correlate(parse_backend_log(LOG.splitlines()), records, datetime(2026, 10, 13, 11, 22, 1), offset_s=0.0)
    verdicts = {r["guid"][-1]: r["verdict"] for r in results}
    assert verdicts["1"].startswith("0x11 : transmise au BA")
    assert "la commutation physique n'est pas prouvée" in verdicts["1"]
    assert verdicts["2"] == "0x12 : acquittée par le BP, non reçue par le BA (NACK d'adresse)"
    assert verdicts["3"] == "0x13 : acquittée par le BP, non reçue par le BA (NACK d'adresse)"


def test_automatic_clock_offset():
    raw, ann, _ = load("cas_installation_2026_10")
    records = decode_offline(raw, ann, RATE)
    _, offset = correlate(parse_backend_log(LOG.splitlines()), records, datetime(2026, 10, 13, 11, 21, 31))
    assert abs(offset - (-30.0 + 0.001)) < 0.01
