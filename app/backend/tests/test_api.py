import csv
import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from captures.models import Capture

BENCH = Path(__file__).resolve().parents[3] / "python_mqtt"

LINES_IN = (
    "0.000 | 2026-10-07T09:00:00.000 | 2026-10-07T09:00:00.003 | data=c02a11840a90003045bec0\n"
    "\n"
    "1.000 | 2026-10-07T09:00:01.000 | 2026-10-07T09:00:01.003 | data=c02a11840a900030ffffc0\n"
)
LINES_OUT = (
    "0.100 | 2026-10-07T09:00:00.100 | 2026-10-07T09:00:00.105 | data=c0112a24c0\n"
    "pas une ligne de log\n"
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


def upload(client, **extra):
    data = {
        "equipment": "equip", "protocol": "nsp", "bench": "banc1",
        "file_in": SimpleUploadedFile("archive_EquipSerialIn.txt", LINES_IN.encode()),
        "file_out": SimpleUploadedFile("archive_EquipSerialOut.txt", LINES_OUT.encode()),
        **extra,
    }
    return client.post("/api/captures/", data, format="multipart")


def test_import_and_summary(client):
    r = upload(client)
    assert r.status_code == 201, r.data
    body = r.json()
    assert body["frame_count"] == 4
    assert body["status_counts"] == {"ok": 1, "crc_error": 1, "too_short": 1, "malformed_line": 1}
    assert {s["name"] for s in body["sources"]} == {"archive_EquipSerialIn.txt", "archive_EquipSerialOut.txt"}
    assert body["protocols"][0]["columns"] == ["DST", "SRC", "CTRL"]


def test_reimport_is_detected(client):
    upload(client)
    r = upload(client)
    assert r.status_code == 409
    assert r.json()["capture"] == Capture.objects.get().pk
    assert upload(client, force="1").status_code == 201


def test_import_validation(client):
    r = client.post("/api/captures/", {"equipment": "", "protocol": "inconnu"}, format="multipart")
    assert r.status_code == 400
    assert set(r.json()) == {"equipment", "protocol", "files"}


def test_frames_sorted_by_emission_time(client):
    cid = upload(client).json()["id"]
    r = client.get(f"/api/frames/?capture={cid}").json()
    assert r["count"] == 4
    statuses = [f["status"] for f in r["results"]]
    # out (09:00:00.100) s'intercale entre les deux demandes ; la ligne illisible hérite de sa date
    assert statuses == ["ok", "too_short", "malformed_line", "crc_error"]


def test_filters(client):
    cid = upload(client).json()["id"]

    def count(qs):
        return client.get(f"/api/frames/?capture={cid}&{qs}").json()["count"]

    assert count("direction=in") == 2
    assert count("status=errors") == 3
    assert count("status=crc_error,ok") == 2
    assert count("f.DST=0x2A") == 2
    assert count("f.DST=0x2A,0x11") == 3
    # la réponse (3 octets) est trop courte mais contient CTRL : il est lu quand même
    assert count("f.CTRL=0x24") == 1
    assert count("from=2026-10-07T07:00:00.500Z") == 1
    assert client.get(f"/api/frames/?capture={cid}&f.DST=zz").status_code == 400
    assert client.get(f"/api/frames/?capture={cid}&status=nimp").status_code == 400
    assert client.get("/api/frames/").status_code == 400


def test_pagination(client):
    cid = upload(client).json()["id"]
    r = client.get(f"/api/frames/?capture={cid}&offset=1&limit=2").json()
    assert [f["status"] for f in r["results"]] == ["too_short", "malformed_line"]
    assert r["count"] == 4


def test_frame_detail_tree(client):
    cid = upload(client).json()["id"]
    first = client.get(f"/api/frames/?capture={cid}&status=ok").json()["results"][0]
    d = client.get(f"/api/frames/{first['id']}/").json()
    assert d["data_hex"] == "2a11840a90003045be"
    assert [(f["name"], f["value"], f["label"]) for f in d["tree"]] == [
        ("DST", 0x2A, "Équipement"), ("SRC", 0x11, "PC banc"), ("CTRL", 0x84, "Requête (poll, cmd 4)")]
    assert d["crc"]["ok"] is True
    assert d["payload"] == {"offset": 3, "size": 4}
    assert d["positions"][0] == 1


def test_malformed_detail_has_text(client):
    cid = upload(client).json()["id"]
    f = client.get(f"/api/frames/?capture={cid}&status=malformed_line").json()["results"][0]
    assert client.get(f"/api/frames/{f['id']}/").json()["text"] == "pas une ligne de log"


def test_export_csv(client):
    cid = upload(client).json()["id"]
    r = client.get(f"/api/captures/{cid}/export/?format=csv&status=ok")
    rows = list(csv.reader(io.StringIO(b"".join(r.streaming_content).decode("utf-8-sig")), delimiter=";"))
    assert rows[0][8:11] == ["DST", "SRC", "CTRL"]
    assert len(rows) == 2 and rows[1][8] == "0x2a"


def test_export_log_roundtrip(client):
    cid = upload(client).json()["id"]
    r = client.get(f"/api/captures/{cid}/export/?format=log&direction=in")
    text = b"".join(r.streaming_content).decode()
    lines = text.splitlines()
    assert len(lines) == 2
    # mêmes dates locales et mêmes octets que le fichier d'origine
    assert lines[0].split("|", 1)[1].strip() == LINES_IN.splitlines()[0].split("|", 1)[1].strip()


def test_delete_capture(client):
    cid = upload(client).json()["id"]
    assert client.delete(f"/api/captures/{cid}/").status_code == 204
    assert not Capture.objects.exists()


def test_protocol_list_and_validate(client):
    protos = {p["name"]: p for p in client.get("/api/protocols/").json()}
    assert protos["nsp"]["active"] and protos["nsp"]["meta"]["columns"] == ["DST", "SRC", "CTRL"]

    nsp_yaml = client.get("/api/protocols/nsp/").json()["yaml"]
    r = client.post("/api/protocols/validate/", {"yaml": nsp_yaml, "hex": "c02a11840a90003045bec0"},
                    format="json").json()
    assert r["ok"] and r["decoded"]["status"] == "ok"

    r = client.post("/api/protocols/validate/", {"yaml": "name: x"}, format="json").json()
    assert not r["ok"] and r["errors"]


def test_protocol_put_rejects_invalid(client):
    r = client.put("/api/protocols/nsp/", {"yaml": "name: nsp\n"}, format="json")
    assert r.status_code == 400
    # le fichier n'a pas été touché
    assert "crc16_ccitt_false" in client.get("/api/protocols/nsp/").json()["yaml"]


@pytest.mark.skipif(not (BENCH / "archive_EquipSerialOut.txt").exists(), reason="logs du banc non générés")
def test_bench_logs_never_crash(client):
    r = client.post("/api/captures/", {
        "equipment": "equip", "protocol": "nsp",
        "files": [SimpleUploadedFile(p.name, p.read_bytes()) for p in sorted(BENCH.glob("archive_*.txt"))],
    }, format="multipart")
    assert r.status_code == 201
    assert r.json()["status_counts"].get("ok", 0) > 0
