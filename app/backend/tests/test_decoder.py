import pytest

from protocols.engine.crc import compute_crc
from protocols.engine.decoder import decode
from protocols.engine.schema import parse_protocol

NSP = parse_protocol("""
name: nsp
framing: slip
min_length: 5
max_length: 32
fields:
  - {name: DST,  offset: 0, size: 1, values: {0x11: PC, 0x2A: EQUIP}}
  - {name: SRC,  offset: 1, size: 1}
  - {name: CTRL, offset: 2, size: 1}
payload: {offset: 3, end: -2}
crc: {type: crc16_ccitt_false, offset: -2, byte_order: little, from: 0, to: -2}
""")

EWC = parse_protocol("""
name: ewc31
framing: none
byte_order: big
min_length: 11
max_length: 64
fields:
  - {name: SYNC, offset: 0, size: 2, expect: 0xEB90}
  - {name: DST,  offset: 2, size: 2}
  - {name: SRC,  offset: 4, size: 2}
  - {name: LEN,  offset: 6, size: 2, display: dec}
  - {name: CMD,  offset: 8, size: 1}
payload: {offset: 9, end: -2}
crc: {type: crc16_xmodem, offset: -2, byte_order: big, from: 0, to: -2}
length: {field: LEN, counts: payload}
""")


def nsp_raw(body: bytes, crc_ok: bool = True) -> bytes:
    crc = compute_crc("crc16_ccitt_false", body)
    if not crc_ok:
        crc ^= 0xFFFF
    return b"\xc0" + body + crc.to_bytes(2, "little") + b"\xc0"


def ewc_raw(payload: bytes, length: int | None = None, sync: int = 0xEB90) -> bytes:
    n = len(payload) if length is None else length
    body = sync.to_bytes(2, "big") + b"\x00\x2a\x00\x11" + n.to_bytes(2, "big") + b"\x05" + payload
    return body + compute_crc("crc16_xmodem", body).to_bytes(2, "big")


def test_nsp_ok():
    d = decode(NSP, nsp_raw(bytes([0x2A, 0x11, 0x84, 0x0A, 0x90])))
    assert d.status == "ok"
    assert d.values() == {"DST": 0x2A, "SRC": 0x11, "CTRL": 0x84}
    assert d.fields[0].label == "EQUIP"
    assert d.payload == (3, 2)
    assert d.crc.ok is True
    assert d.crc.offset == 5


def test_nsp_crc_error():
    d = decode(NSP, nsp_raw(bytes([0x2A, 0x11, 0x84]), crc_ok=False))
    assert d.status == "crc_error"
    assert d.crc.ok is False
    # le décodage reste fidèle : les champs sont quand même lus
    assert d.values()["DST"] == 0x2A


def test_crc_check_can_be_disabled():
    spec = parse_protocol("""
name: p
framing: none
min_length: 3
max_length: 8
fields: [{name: A, offset: 0, size: 1}]
crc: {type: crc16_ccitt_false, offset: -2, check: false}
""")
    d = decode(spec, b"\x01\xff\xff")
    assert d.status == "ok"
    assert d.crc.ok is None


def test_empty():
    assert decode(NSP, b"").status == "empty"
    assert decode(NSP, b"\xc0\xc0").status == "empty"


def test_too_short_decodes_available_fields():
    d = decode(NSP, bytes.fromhex("c0112ac0"))
    assert d.status == "too_short"
    assert d.values() == {"DST": 0x11, "SRC": 0x2A}
    assert d.fields[2].value is None
    assert d.crc is None


def test_too_long_is_refused():
    d = decode(NSP, b"\xc0" + b"\x00" * 5000 + b"\xc0")
    assert d.status == "too_long"
    assert d.fields == []


def test_framing_error():
    d = decode(NSP, nsp_raw(bytes([0x2A, 0x11, 0x84]))[:-1])  # c0 final manquant
    assert d.status == "framing_error"
    assert d.values()["CTRL"] == 0x84


def test_multi_byte_big_endian_and_length():
    d = decode(EWC, ewc_raw(b"\x01\x02\x03"))
    assert d.status == "ok", d.issues
    assert d.values() == {"SYNC": 0xEB90, "DST": 0x2A, "SRC": 0x11, "LEN": 3, "CMD": 5}


def test_length_mismatch():
    d = decode(EWC, ewc_raw(b"\x01\x02\x03", length=7))
    assert d.status == "length_mismatch"


def test_header_mismatch():
    d = decode(EWC, ewc_raw(b"\x01", sync=0x1234))
    assert d.status == "header_mismatch"
    assert d.fields[0].issue


def test_most_severe_status_wins():
    raw = bytearray(ewc_raw(b"\x01\x02", sync=0x1234, length=9))
    raw[-1] ^= 0xFF  # + CRC faux
    d = decode(EWC, bytes(raw))
    assert d.status == "header_mismatch"
    assert {i.code for i in d.issues} == {"header_mismatch", "length_mismatch", "crc_error"}


def test_positions_map_to_raw_bytes():
    d = decode(NSP, nsp_raw(bytes([0x2A, 0x11, 0x84])))
    assert d.positions[0] == 1  # DST est le 2e octet brut (après c0)


@pytest.mark.parametrize("raw", [b"\xdb", b"\xc0\xdb\xc0", bytes(range(256)), b"\xc0" * 100])
def test_never_raises(raw):
    decode(NSP, raw)
    decode(EWC, raw)
