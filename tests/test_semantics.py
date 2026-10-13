from essensys_i2c_sniffer.semantics import DEFAULT_PROFILES, StateTracker, decode_payload


def cmd(commands, kind, index):
    return next(c for c in commands if c["type"] == kind and c["index"] == index)


def test_lamp_on_decoded():
    commands, anomalies, _ = decode_payload(1, bytes([0, 0x40, 0, 0, 0, 0, 0, 0]), 0x12)
    assert cmd(commands, "lampe", 6)["action"] == "ON" and not anomalies


def test_off_has_priority_over_on():
    commands, _, _ = decode_payload(1, bytes([0x01, 0x01, 0, 0, 0x01, 0x01, 0, 0]), 0x11)
    assert cmd(commands, "lampe", 0) == {"type": "lampe", "index": 0, "action": "OFF", "conflict": True}
    assert cmd(commands, "variateur", 0)["action"] == "OFF"


def test_up_has_priority_over_down():
    commands, _, _ = decode_payload(1, bytes([0, 0, 0, 0, 0, 0, 0x04, 0x04]), 0x11)
    c = cmd(commands, "volet", 2)
    assert c["action"] == "montée/ouverture" and c["conflict"]


def test_out_of_range_for_profile():
    # BA chambres : 7 relais lampes (index 0-6).
    commands, anomalies, _ = decode_payload(1, bytes([0, 0, 0, 0x01, 0, 0, 0, 0]), 0x12)
    assert not commands and any("hors plage" in a for a in anomalies)


def test_profiles_from_hard_c():
    assert (DEFAULT_PROFILES[0x11].lamps, DEFAULT_PROFILES[0x12].lamps, DEFAULT_PROFILES[0x13].lamps) == (5, 7, 13)


def test_no_command_note():
    commands, anomalies, fields = decode_payload(1, bytes(8), 0x11)
    assert commands == [] and anomalies == [] and fields["note"] == "aucune sortie commandée"


def test_actions_reserved_bits():
    _, anomalies, fields = decode_payload(5, bytes([0x82]), 0x12)
    assert fields["octet"] == 0x82 and any("réservés" in a for a in anomalies)


def test_config_padding_kept_raw():
    _, _, fields = decode_payload(2, bytes([1, 0, 2, 1, 7, 7, 7, 7]), 0x12)
    assert len(fields["modes_variateurs"]) == 4 and fields["bourrage"] == "07070707"
    _, _, fields = decode_payload(3, bytes([0] + [5] * 15), 0x13)
    assert fields["extinction_min"][0]["libelle"] == "pas d'extinction automatique"


def test_state_inferred_unknown_by_default():
    st = StateTracker()
    st.apply(0x11, [{"type": "lampe", "index": 0, "action": "ON"}])
    summary = st.summary()
    assert summary["inferred"] is True
    assert summary["ba"]["0x11"]["lampes"][:2] == ["ON", "inconnu"]
    assert summary["ba"]["0x12"]["lampes"] == ["inconnu"] * 7
