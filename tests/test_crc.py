from essensys_i2c_sniffer.crc import crc16, crc16_le


def test_crc16_modbus_check_value():
    # Valeur de contrôle normalisée du CRC-16/MODBUS.
    assert crc16(b"123456789") == 0x4B37


def test_crc_little_endian_on_wire():
    assert crc16_le(b"123456789") == bytes([0x37, 0x4B])


def test_crc_of_empty_is_init():
    assert crc16(b"") == 0xFFFF
