from protocols.engine.framing import deframe


def test_none_framing_is_identity():
    r = deframe(b"\x01\x02\xc0", "none")
    assert r.data == b"\x01\x02\xc0"
    assert r.positions == [0, 1, 2]
    assert r.issues == []


def test_slip_strips_delimiters():
    r = deframe(bytes.fromhex("c0112a84c0"), "slip")
    assert r.data == bytes.fromhex("112a84")
    assert r.positions == [1, 2, 3]
    assert r.issues == []


def test_slip_unescapes():
    # db dc -> c0 ; db dd -> db
    r = deframe(bytes.fromhex("c001dbdc02dbdd03c0"), "slip")
    assert r.data == bytes.fromhex("01c002db03")
    # chaque octet décodé pointe vers le premier octet de sa séquence dans le brut
    assert r.positions == [1, 2, 4, 5, 7]
    assert r.issues == []


def test_slip_missing_end_is_reported_but_decoded():
    r = deframe(bytes.fromhex("c0112a"), "slip")
    assert r.data == bytes.fromhex("112a")
    assert len(r.issues) == 1


def test_slip_missing_start_is_tolerated():
    # RFC 1055 : le c0 de début est optionnel
    r = deframe(bytes.fromhex("112ac0"), "slip")
    assert r.data == bytes.fromhex("112a")
    assert r.issues == []


def test_slip_bad_escape_kept_as_is():
    r = deframe(bytes.fromhex("c001db7702c0"), "slip")
    assert r.data == bytes.fromhex("01db7702")
    assert len(r.issues) == 1


def test_slip_trailing_escape():
    r = deframe(bytes.fromhex("c001dbc0"), "slip")
    assert r.data == bytes.fromhex("01db")
    assert len(r.issues) == 1


def test_slip_delimiter_inside_frame():
    r = deframe(bytes.fromhex("c00102c00304c0"), "slip")
    assert r.data == bytes.fromhex("01020304")
    assert len(r.issues) == 1


def test_slip_only_delimiters():
    r = deframe(bytes.fromhex("c0c0"), "slip")
    assert r.data == b""
    assert r.issues == []
