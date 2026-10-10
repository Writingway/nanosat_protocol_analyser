"""Import de fichiers de logs (in = demandes, out = réponses) dans une nouvelle capture."""
import hashlib
import re
from dataclasses import dataclass
from typing import IO

from django.db import transaction
from django.db.models import Max, Min
from django.utils import timezone

from .ingest import Ingestor
from .models import Capture, Source


class DuplicateImport(Exception):
    def __init__(self, capture: Capture):
        super().__init__(f"Ces fichiers ont déjà été importés (capture « {capture.name} »).")
        self.capture = capture


@dataclass
class LogFile:
    name: str
    content: IO[bytes]
    direction: str  # "in" ou "out"


_DIRECTION_RE = re.compile(r"(in|out)$", re.IGNORECASE)


def guess_direction(filename: str) -> str | None:
    """archive_EquipSerialIn.txt → in ; archive_EquipSerialOut.txt → out."""
    stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    m = _DIRECTION_RE.search(stem)
    return m.group(1).lower() if m else None


def _fingerprint(files: list[LogFile]) -> str:
    h = hashlib.sha256()
    for f in sorted(files, key=lambda f: f.direction):
        f.content.seek(0)
        h.update(f.direction.encode())
        for chunk in iter(lambda: f.content.read(1 << 20), b""):  # noqa: B023
            h.update(chunk)
        f.content.seek(0)
    return h.hexdigest()


def import_logs(files: list[LogFile], *, equipment: str, protocol: str, bench: str = "",
                name: str | None = None, force: bool = False) -> Capture:
    sha = _fingerprint(files)
    if not force:
        existing = Capture.objects.filter(file_sha256=sha).first()
        if existing:
            raise DuplicateImport(existing)

    # Tout ou rien : un import qui échoue au milieu ne laisse pas de capture à moitié remplie.
    with transaction.atomic():
        capture = Capture.objects.create(
            name=name or " + ".join(f.name for f in files),
            kind=Capture.Kind.IMPORT, state=Capture.State.ENDED,
            started_at=timezone.now(), file_sha256=sha,
        )
        ingestor = Ingestor(capture, batch_size=2000)
        for f in files:
            source, _ = Source.objects.get_or_create(
                kind=Source.Kind.FILE, name=f.name, bench=bench, equipment=equipment,
                defaults={"protocol": protocol},
            )
            if source.protocol != protocol:
                source.protocol = protocol
                source.save(update_fields=["protocol"])
            for raw_line in f.content:
                ingestor.add(raw_line.decode("utf-8", errors="replace"), source, f.direction)
        ingestor.flush()

        bounds = capture.frames.aggregate(start=Min("ts"), end=Max("ts"))
        capture.started_at = bounds["start"] or capture.started_at
        capture.ended_at = bounds["end"] or capture.started_at
        capture.frame_count = ingestor.total
        capture.save(update_fields=["started_at", "ended_at", "frame_count"])
    return capture
