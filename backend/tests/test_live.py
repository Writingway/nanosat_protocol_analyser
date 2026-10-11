import pytest
from django.conf import settings
from rest_framework.test import APIClient

from captures.live import IngestConfig, TopicMatcher, load_config
from captures.live_ingester import LiveIngester
from captures.models import Capture, CaptureEvent, Frame, LiveControl, Source
from protocols.engine.schema import ProtocolError

LINE = "0.000 | 2026-10-07T09:00:00.000 | 2026-10-07T09:00:00.003 | data=c02a11840a90003045bec0"


def test_topic_matcher():
    m = TopicMatcher(["{bench}/{equipment}/serial/{direction}", "{equipment}/serial/{direction}"])
    info = m.match("equip/serial/in")
    assert (info.bench, info.equipment, info.direction) == ("", "equip", "in")
    info = m.match("banc1/gyro/serial/out")
    assert (info.bench, info.equipment, info.direction) == ("banc1", "gyro", "out")
    assert m.match("equip/serial/autre") is None
    assert m.match("a/b/c/serial/in") is None


def test_project_config_is_valid():
    cfg = load_config(settings.INGEST_CONFIG)
    assert cfg.equipments["equip"] == "nsp"


def test_config_errors_are_readable(tmp_path):
    p = tmp_path / "ingest.yaml"
    p.write_text("subscribe: ['#']\ntopics: ['{equipment}/serial']\nbrokr: {}\n")
    with pytest.raises(ProtocolError) as exc:
        load_config(p)
    text = " ".join(exc.value.errors)
    assert "direction" in text and "brokr" in text


pytestmark = pytest.mark.django_db


def make_ingester():
    cfg = IngestConfig(subscribe=["#"], topics=["{bench}/{equipment}/serial/{direction}",
                                               "{equipment}/serial/{direction}"],
                       equipments={"equip": "nsp"})
    return LiveIngester(cfg)


def test_start_stop_api():
    c = APIClient()
    r = c.post("/api/live/start/", {"name": "essai"}, format="json")
    assert r.status_code == 201 and r.json()["capture"]["name"] == "essai"
    assert c.post("/api/live/start/", {}, format="json").status_code == 409
    state = c.get("/api/live/").json()
    assert state["recording"] and not state["ingester_alive"]
    r = c.post("/api/live/stop/", format="json")
    assert not r.json()["recording"]
    cap = Capture.objects.get()
    assert cap.state == "ended" and cap.ended_at


def test_messages_ignored_without_capture():
    ing = make_ingester()
    ing.on_message("equip/serial/in", LINE.encode())
    ing.run_once(timeout=0)
    assert ing.ignored == 1 and not Frame.objects.exists()


def test_live_ingestion_flow():
    APIClient().post("/api/live/start/", {}, format="json")
    ing = make_ingester()
    ing.run_once(timeout=0)  # lit LiveControl → capture suivie
    ing.on_connection(True, "localhost:1883")
    ing.on_message("equip/serial/in", LINE.encode())
    ing.on_message("banc1/inconnu/serial/out", LINE.encode())
    ing.on_message("topic/hors/motif", b"x")
    ing.run_once(timeout=0)
    ing.ingestor.flush()

    frames = Frame.objects.order_by("id")
    assert [f.status for f in frames] == ["ok", "unknown_protocol"]
    assert frames[0].direction == "in" and frames[1].direction == "out"
    assert Source.objects.get(equipment="inconnu").bench == "banc1"
    assert ing.ignored == 1

    ing.on_connection(False, "coupure")
    ing.run_once(timeout=0)
    ctl = LiveControl.get()
    assert not ctl.connected and "coupure" in ctl.last_error
    assert list(CaptureEvent.objects.values_list("kind", flat=True)) == ["connected", "disconnected"]

    APIClient().post("/api/live/stop/", format="json")
    ing._next_control = 0
    ing.run_once(timeout=0)
    assert ing.ingestor is None
