"""Conversion modèles → JSON. Fonctions simples plutôt que des Serializer DRF : tout est en lecture."""
from django.db.models import Count

from protocols.engine.decoder import decode
from protocols.engine.framing import deframe
from protocols.engine.schema import ProtocolError, ProtocolSpec
from protocols.models import ProtocolVersion
from protocols.registry import spec_for_version

from ..models import Capture, Frame, Source


def safe_spec(version_id: int | None) -> ProtocolSpec | None:
    if version_id is None:
        return None
    try:
        return spec_for_version(version_id)
    except (ProtocolVersion.DoesNotExist, ProtocolError):
        return None


def source_json(s: Source) -> dict:
    return {"id": s.id, "kind": s.kind, "name": s.name, "bench": s.bench,
            "equipment": s.equipment, "protocol": s.protocol}


def capture_json(c: Capture) -> dict:
    return {"id": c.id, "name": c.name, "kind": c.kind, "state": c.state,
            "started_at": c.started_at, "ended_at": c.ended_at,
            "frame_count": c.frame_count, "created_at": c.created_at}


def protocol_meta(version_id: int, spec: ProtocolSpec, sha: str) -> dict:
    """Ce dont l'IHM a besoin pour afficher les colonnes et libellés d'un protocole."""
    return {
        "version_id": version_id, "sha256": sha, "name": spec.name, "label": spec.label,
        "columns": spec.columns,
        "fields": [{"name": f.name, "display": f.display, "size": f.size, "description": f.description,
                    "values": [[v, lbl] for v, lbl in f.values.items()]} for f in spec.fields],
    }


def capture_detail_json(c: Capture) -> dict:
    # Une seule passe sur les frames de la capture pour tout le résumé.
    groups = (c.frames.order_by().values("source_id", "protocol_version_id", "status")
              .annotate(n=Count("id")))
    sources, versions, statuses = set(), set(), {}
    for g in groups:
        sources.add(g["source_id"])
        if g["protocol_version_id"]:
            versions.add(g["protocol_version_id"])
        statuses[g["status"]] = statuses.get(g["status"], 0) + g["n"]

    protocols = []
    for pv in ProtocolVersion.objects.filter(id__in=versions):
        spec = safe_spec(pv.id)
        if spec:
            protocols.append(protocol_meta(pv.id, spec, pv.sha256))

    return {
        **capture_json(c),
        "sources": [source_json(s) for s in Source.objects.filter(id__in=sources)],
        "protocols": protocols,
        "status_counts": statuses,
        "events": [{"ts": e.ts, "kind": e.kind, "message": e.message} for e in c.events.all()],
    }


def frame_json(f: Frame) -> dict:
    raw = bytes(f.raw)
    spec = safe_spec(f.protocol_version_id) if f.status != "malformed_line" else None
    length = len(deframe(raw, spec.framing).data) if spec else len(raw)
    return {
        "id": f.id, "ts": f.ts, "ts_bench_rx": f.ts_bench_rx, "received_at": f.received_at,
        "direction": f.direction, "source": f.source_id, "protocol_version": f.protocol_version_id,
        "status": f.status, "detail": f.detail, "fields": f.fields, "length": length,
    }


def frame_detail_json(f: Frame) -> dict:
    """Frame + arbre complet, re-décodé avec la version de YAML figée à l'ingestion."""
    out = frame_json(f)
    raw = bytes(f.raw)
    out["raw_hex"] = raw.hex()
    out["capture"] = f.capture_id
    if f.status == "malformed_line":
        out["text"] = raw.decode("utf-8", errors="replace")
        return out
    spec = safe_spec(f.protocol_version_id)
    if spec is None:
        return out
    d = decode(spec, raw)
    out.update({
        "protocol": {"name": spec.name, "label": spec.label, "framing": spec.framing},
        "data_hex": d.data.hex(),
        "positions": d.positions,
        "tree": [
            {"name": x.name, "offset": x.offset, "size": x.size, "value": x.value, "label": x.label,
             "display": x.display, "description": x.description, "issue": x.issue}
            for x in d.fields
        ],
        "payload": {"offset": d.payload[0], "size": d.payload[1]} if d.payload else None,
        "crc": None if d.crc is None else {
            "offset": d.crc.offset, "size": d.crc.size, "read": d.crc.read, "computed": d.crc.computed,
            "ok": d.crc.ok, "covers": list(d.crc.covers),
        },
        "issues": [{"code": i.code, "message": i.message} for i in d.issues],
    })
    return out
