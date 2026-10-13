from essensys_i2c_sniffer.annotations import parse_line


def test_simple_events():
    assert parse_line("210-210 i2c-1: Start").kind == "start"
    assert parse_line("1500-1500 i2c-1: Start repeat").kind == "rstart"
    assert parse_line("425-425 i2c-1: Stop").kind == "stop"
    assert parse_line("395-415 i2c-1: NACK").kind == "nack"


def test_valued_events():
    e = parse_line("235-375 i2c-1: Address write: 12")
    assert (e.kind, e.value, e.start, e.end) == ("addr_w", 0x12, 235, 375)
    assert parse_line("1700-1860 i2c-1: Data read: 05").value == 5


def test_rw_bit_and_other_decoders_ignored():
    assert parse_line("375-395 i2c-1: Write") is None
    assert parse_line("500-15500 timing-1: 15.000 ms (66.667 Hz)") is None
    assert parse_line("") is None


def test_truncated_line_is_invalid_not_exception():
    e = parse_line("12-3")
    assert e.kind == "invalid" and e.raw == "12-3"
