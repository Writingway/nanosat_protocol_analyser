import pytest

from protocols.engine.crc import CRC_ALGORITHMS, compute_crc

# Valeurs de contrôle officielles ("check") du catalogue CRC RevEng sur b"123456789".
CHECK_VALUES = {
    "crc16_ccitt_false": 0x29B1,
    "crc16_xmodem": 0x31C3,
    "crc16_modbus": 0x4B37,
    "crc8": 0xF4,
}


@pytest.mark.parametrize("name,expected", CHECK_VALUES.items())
def test_check_values(name, expected):
    assert compute_crc(name, b"123456789") == expected


def test_sizes():
    assert CRC_ALGORITHMS["crc16_ccitt_false"].size == 2
    assert CRC_ALGORITHMS["crc8"].size == 1


def test_empty_input_returns_init():
    assert compute_crc("crc16_ccitt_false", b"") == 0xFFFF


def test_matches_bench_generator():
    """Même CRC que python_mqtt/gen_logs.py pour une requête NSP du banc."""
    body = bytes([0x2A, 0x11, 0x84, 0x0A, 0x90, 0x00, 0x30])
    crc = compute_crc("crc16_ccitt_false", body)
    assert crc.to_bytes(2, "little") == bytes.fromhex("45be")
