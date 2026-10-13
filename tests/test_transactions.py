from essensys_i2c_sniffer.annotations import parse_line
from essensys_i2c_sniffer.transactions import build


def tx(lines, end=-1):
    return build([e for e in (parse_line(l) for l in lines) if e], end)


def test_write_then_read_is_one_transaction():
    out = tx(["1-1 i2c-1: Start", "2-3 i2c-1: Address write: 11", "4-4 i2c-1: ACK", "5-6 i2c-1: Data write: 05", "7-7 i2c-1: ACK",
              "8-8 i2c-1: Start repeat", "9-10 i2c-1: Address read: 11", "11-11 i2c-1: ACK", "12-13 i2c-1: Data read: 05", "14-14 i2c-1: NACK",
              "15-15 i2c-1: Stop"])
    assert len(out) == 1
    t = out[0]
    assert [p.direction for p in t.phases] == ["W", "R"]
    assert t.phases[0].data == [5] and t.phases[0].addr_ack is True
    assert t.phases[1].acks == [False] and t.stopped


def test_address_nack_recorded():
    t = tx(["1-1 i2c-1: Start", "2-3 i2c-1: Address write: 12", "4-4 i2c-1: NACK", "5-5 i2c-1: Stop"])[0]
    assert t.phases[0].addr_ack is False


def test_start_without_stop_is_interrupted():
    out = tx(["1-1 i2c-1: Start", "2-3 i2c-1: Address write: 11", "10-10 i2c-1: Start", "11-12 i2c-1: Address write: 12", "13-13 i2c-1: ACK", "14-14 i2c-1: Stop"])
    assert len(out) == 2
    assert any("START sans STOP" in a for a in out[0].anomalies)


def test_flush_at_end_of_capture():
    out = tx(["1-1 i2c-1: Start"], end=99)
    assert out[0].end == 99 and any("fin de capture" in a for a in out[0].anomalies)
