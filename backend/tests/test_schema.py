import pytest

from protocols.engine.schema import ProtocolError, parse_protocol

NSP = """
name: nsp
label: NSP
framing: slip
min_length: 5
max_length: 64
fields:
  - {name: DST,  offset: 0, size: 1, values: {0x11: PC, 0x2A: EQUIP}}
  - {name: SRC,  offset: 1, size: 1}
  - {name: CTRL, offset: 2, size: 1}
payload: {offset: 3, end: -2}
crc: {type: crc16_ccitt_false, offset: -2, byte_order: little, from: 0, to: -2}
"""


def test_valid_protocol():
    spec = parse_protocol(NSP)
    assert spec.name == "nsp"
    assert [f.name for f in spec.fields] == ["DST", "SRC", "CTRL"]
    assert spec.fields[0].values == {0x11: "PC", 0x2A: "EQUIP"}
    assert spec.crc.size == 2
    assert spec.crc.check is True
    # colonnes par défaut = tous les champs
    assert spec.columns == ["DST", "SRC", "CTRL"]


def errors_of(text: str) -> list[str]:
    with pytest.raises(ProtocolError) as exc:
        parse_protocol(text)
    return exc.value.errors


def test_yaml_syntax_error_has_line():
    errs = errors_of("name: nsp\nfields: [\n")
    assert "ligne" in errs[0]


def test_not_a_mapping():
    assert errors_of("- a\n- b\n")


def test_missing_required_key():
    errs = errors_of("name: x\nmin_length: 1\nmax_length: 2\n")
    assert any("fields" in e and "obligatoire" in e for e in errs)


def test_unknown_key_is_reported():
    errs = errors_of(NSP + "colums: [DST]\n")
    assert any("colums" in e and "inconnue" in e for e in errs)


def test_negative_offset():
    errs = errors_of(NSP.replace("{name: SRC,  offset: 1", "{name: SRC,  offset: -1"))
    assert any("fields[1].offset" in e for e in errs)


def test_overlapping_fields():
    errs = errors_of(NSP.replace("{name: SRC,  offset: 1, size: 1}", "{name: SRC,  offset: 0, size: 2}"))
    assert any("chevauche" in e for e in errs)


def test_duplicate_field_names():
    errs = errors_of(NSP.replace("name: SRC", "name: DST"))
    assert any("double" in e for e in errs)


def test_unknown_crc_type():
    errs = errors_of(NSP.replace("crc16_ccitt_false", "crc99"))
    assert any("crc.type" in e for e in errs)


def test_header_longer_than_min_length():
    errs = errors_of(NSP.replace("min_length: 5", "min_length: 2"))
    assert any("min_length" in e for e in errs)


def test_max_below_min():
    errs = errors_of(NSP.replace("max_length: 64", "max_length: 3"))
    assert any("max_length" in e for e in errs)


def test_unknown_column():
    errs = errors_of(NSP + "columns: [DST, FOO]\n")
    assert any("FOO" in e for e in errs)


def test_value_too_big_for_field():
    errs = errors_of(NSP.replace("0x2A: EQUIP", "0x1FF: EQUIP"))
    assert any("DST" in e for e in errs)


def test_bad_name_format():
    errs = errors_of(NSP.replace("name: nsp", "name: 'mon protocole'"))
    assert any("name" in e for e in errs)


def test_length_field_must_exist():
    errs = errors_of(NSP + "length: {field: LEN, counts: payload}\n")
    assert any("LEN" in e for e in errs)


def test_messages_are_french():
    errs = errors_of(NSP.replace("size: 1}", "size: abc}", 1))
    assert any("entier" in e for e in errs)
