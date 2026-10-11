"""Chaîne commune aux imports de fichiers et à la capture live :

    ligne de log → lecture → décodage (YAML) → tampon → écriture en base par lots → notification

L'écriture par lots (bulk_create) évite un aller-retour base par frame quand le flux monte.
Après chaque lot, un NOTIFY PostgreSQL prévient l'API, qui pousse l'info aux navigateurs (SSE).
"""
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection
from django.db.models import F
from django.utils import timezone

from protocols.engine.decoder import decode
from protocols.registry import get_registry

from .logline import parse_line
from .models import Capture, Frame, Source

log = logging.getLogger(__name__)

NOTIFY_CHANNEL = "analyseur_frames"


def notify(payload: dict) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT pg_notify(%s, %s)", [NOTIFY_CHANNEL, json.dumps(payload)])


class Ingestor:
    def __init__(self, capture: Capture, batch_size: int = 500):
        self.capture = capture
        self.batch_size = batch_size
        self.tz = ZoneInfo(settings.LOG_TIMEZONE)
        self.registry = get_registry()
        self._buffer: list[Frame] = []
        # Dernière date lue par source : sert aux lignes illisibles qui n'ont pas de date.
        self._last_ts: dict[int, datetime] = {}
        self.total = 0

    def add(self, line: str, source: Source, direction: str, received_at: datetime | None = None) -> None:
        received_at = received_at or timezone.now()
        parsed = parse_line(line, self.tz)
        if parsed is None:
            return

        ts = parsed.ts_emit or self._last_ts.get(source.id) or received_at
        self._last_ts[source.id] = ts
        frame = Frame(capture=self.capture, source=source, direction=direction, ts=ts,
                      ts_bench_rx=parsed.ts_bench_rx, received_at=received_at, raw=parsed.raw)

        loaded = self.registry.get(source.protocol)
        if parsed.error:
            frame.status, frame.detail = "malformed_line", parsed.error
        elif loaded is None:
            frame.status = "unknown_protocol"
            frame.detail = f"aucun protocole « {source.protocol} » chargé"
        else:
            decoded = decode(loaded.spec, parsed.raw)
            frame.protocol_version_id = self.registry.version_id(loaded)
            frame.status, frame.detail, frame.fields = decoded.status, decoded.detail, decoded.values()

        self._buffer.append(frame)
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self) -> int:
        """Écrit le tampon. Renvoie le nombre de frames écrites."""
        if not self._buffer:
            return 0
        batch, self._buffer = self._buffer, []
        Frame.objects.bulk_create(batch)
        Capture.objects.filter(pk=self.capture.pk).update(frame_count=F("frame_count") + len(batch))
        self.total += len(batch)
        notify({"type": "frames", "capture": self.capture.pk, "last_id": batch[-1].pk, "count": len(batch)})
        return len(batch)
