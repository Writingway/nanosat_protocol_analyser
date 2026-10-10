"""Export d'une capture (avec les filtres courants) en CSV ou au format log ré-importable."""
import csv
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import StreamingHttpResponse

from ..models import Source
from .serializers import safe_spec


class _Echo:
    """Pseudo-fichier pour csv.writer : renvoie la ligne au lieu de l'écrire."""

    def write(self, value):
        return value


def _rows(qs):
    return qs.select_related(None).iterator(chunk_size=2000)


def export_csv(capture, qs, field_names: list[str]) -> StreamingHttpResponse:
    sources = {s.id: s for s in Source.objects.filter(frames__capture=capture).distinct()}
    writer = csv.writer(_Echo(), delimiter=";")

    def generate():
        yield "﻿"  # BOM : Excel reconnaît l'UTF-8
        yield writer.writerow(["id", "horodatage", "sens", "banc", "equipement", "source", "statut",
                               "detail", *field_names, "octets_hex"])
        for f in _rows(qs):
            s = sources.get(f.source_id)
            values = [f"{f.fields[n]:#x}" if n in f.fields else "" for n in field_names]
            yield writer.writerow([f.id, f.ts.isoformat(timespec="milliseconds"), f.direction,
                                   s.bench if s else "", s.equipment if s else "", s.name if s else "",
                                   f.status, f.detail, *values, bytes(f.raw).hex()])

    resp = StreamingHttpResponse(generate(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="capture_{capture.pk}.csv"'
    return resp


def export_log(capture, qs, direction: str | None) -> StreamingHttpResponse:
    """Même format que les logs du banc : le fichier produit peut être ré-importé."""
    tz = ZoneInfo(settings.LOG_TIMEZONE)

    def local(dt):
        return dt.astimezone(tz).replace(tzinfo=None).isoformat(timespec="milliseconds")

    def generate():
        t0 = None
        for f in _rows(qs):
            raw = bytes(f.raw)
            if f.status == "malformed_line":  # on restitue la ligne d'origine
                yield raw.decode("utf-8", errors="replace") + "\n"
                continue
            t0 = t0 or f.ts
            rx = local(f.ts_bench_rx) if f.ts_bench_rx else local(f.ts)
            yield f"{(f.ts - t0).total_seconds():.3f} | {local(f.ts)} | {rx} | data={raw.hex()}\n"

    suffix = {"in": "In", "out": "Out"}.get(direction or "", "")
    resp = StreamingHttpResponse(generate(), content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="capture_{capture.pk}_Serial{suffix}.txt"'
    return resp


def field_names_of(protocol_version_ids) -> list[str]:
    names: list[str] = []
    for vid in protocol_version_ids:
        spec = safe_spec(vid)
        for f in spec.fields if spec else []:
            if f.name not in names:
                names.append(f.name)
    return names
