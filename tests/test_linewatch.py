from essensys_i2c_sniffer.linewatch import LineWatch


def watch():
    return LineWatch({"SCL": 0, "SDA": 1}, samplerate=1000, threshold_ms=10)


def test_stuck_sda_detected_across_chunks():
    lw = watch()
    data = bytes([3]) * 5 + bytes([1]) * 15 + bytes([3]) * 5  # SDA basse 15 ms à 1 kHz
    events = []
    for i in range(0, len(data), 4):
        events += lw.feed(data[i:i + 4])
    assert len(events) == 1
    e = events[0]
    assert (e["line"], e["sample"], e["duration_ms"]) == ("SDA", 5, 15.0)


def test_short_low_ignored():
    lw = watch()
    assert lw.feed(bytes([3]) * 5 + bytes([2]) * 10 + bytes([3]) * 5) == []  # SCL basse 10 ms = seuil


def test_ongoing_at_end():
    lw = watch()
    lw.feed(bytes([3]) * 2 + bytes([2]) * 20)
    events = lw.flush()
    assert events[0]["line"] == "SCL" and events[0]["ongoing_at_end"] is True
