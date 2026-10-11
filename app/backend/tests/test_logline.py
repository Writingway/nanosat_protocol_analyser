from zoneinfo import ZoneInfo

from captures.logline import MAX_LINE_BYTES, parse_line

TZ = ZoneInfo("Europe/Paris")


def test_valid_line():
    ll = parse_line("0.000 | 2026-10-07T09:00:00.000 | 2026-10-07T09:00:00.004 | data=c0112ac0\n", TZ)
    assert ll.error is None
    assert ll.raw == bytes.fromhex("c0112ac0")
    assert ll.ts_emit.isoformat() == "2026-10-07T09:00:00+02:00"
    assert (ll.ts_bench_rx - ll.ts_emit).total_seconds() == 0.004


def test_blank_line_is_not_a_frame():
    assert parse_line("   \n", TZ) is None


def test_spaces_inside_hex_are_ignored():
    assert parse_line("0 | x | y | data=c0 11 2a c0", TZ).raw == bytes.fromhex("c0112ac0")


def test_empty_data():
    ll = parse_line("0 | 2026-10-07T09:00:00 | 2026-10-07T09:00:00 | data=", TZ)
    assert ll.error is None and ll.raw == b""


def test_no_data_marker():
    ll = parse_line("pas une ligne de log", TZ)
    assert ll.error and ll.raw == b"pas une ligne de log"
    assert ll.ts_emit is None


def test_invalid_hex():
    assert parse_line("0 | a | b | data=c0zz", TZ).error


def test_odd_hex_length():
    assert parse_line("0 | a | b | data=c01", TZ).error


def test_bad_dates_still_decode():
    ll = parse_line("0 | hier | demain | data=c0", TZ)
    assert ll.error is None and ll.ts_emit is None


def test_explicit_timezone_is_kept():
    ll = parse_line("0 | 2026-10-07T07:00:00+00:00 | x | data=c0", TZ)
    assert ll.ts_emit.utcoffset().total_seconds() == 0


def test_huge_line_is_truncated():
    ll = parse_line("0 | a | b | data=" + "00" * MAX_LINE_BYTES, TZ)
    assert ll.error and len(ll.raw) == MAX_LINE_BYTES
