"""CRC-16 du protocole BP↔BA.

Reproduction de ``us_CalculerCRCSurTrame`` (``crc.c`` du firmware SC944D et des
BA v1.7) : CRC-16/MODBUS, initialisation 0xFFFF, polynôme réfléchi 0xA001,
sans XOR final. Le CRC est transmis poids faible en premier.
"""


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def crc16_le(data: bytes) -> bytes:
    """CRC tel qu'il est placé sur le fil (poids faible, poids fort)."""
    value = crc16(data)
    return bytes((value & 0xFF, (value >> 8) & 0xFF))
