import os
import re
import tempfile

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from captures.api.serializers import protocol_meta

from .engine.decoder import decode
from .engine.schema import ProtocolError, parse_protocol
from .registry import get_registry

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _status_with_meta() -> list[dict]:
    reg = get_registry()
    loaded = reg.all()
    out = []
    for st in reg.status():
        lp = loaded.get(st["name"]) if st["active"] else None
        if lp:
            st["meta"] = protocol_meta(reg.version_id(lp), lp.spec, lp.sha256)
        out.append(st)
    return out


class ProtocolListView(APIView):
    def get(self, request):
        return Response(_status_with_meta())


class ProtocolDetailView(APIView):
    """Lecture / écriture du YAML d'un protocole (éditeur de l'IHM)."""

    def get(self, request, name):
        reg = get_registry()
        path = reg.directory / f"{name}.yaml"
        if not _NAME_RE.match(name) or not path.exists():
            return Response({"detail": "protocole inconnu"}, status=status.HTTP_404_NOT_FOUND)
        st = next((s for s in reg.status() if s["file"] == path.name), None)
        return Response({"name": name, "yaml": path.read_text(encoding="utf-8"), "status": st})

    def put(self, request, name):
        """Enregistre le YAML seulement s'il est valide : le fichier n'est jamais remplacé par un YAML cassé."""
        if not _NAME_RE.match(name):
            return Response({"errors": ["nom de protocole invalide"]}, status=status.HTTP_400_BAD_REQUEST)
        text = request.data.get("yaml", "")
        try:
            spec = parse_protocol(text)
        except ProtocolError as exc:
            return Response({"errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        if spec.name != name:
            return Response({"errors": [f"name : vaut « {spec.name} », attendu « {name} »"]},
                            status=status.HTTP_400_BAD_REQUEST)
        reg = get_registry()
        # Écriture atomique : fichier temporaire puis renommage.
        fd, tmp = tempfile.mkstemp(dir=reg.directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, reg.directory / f"{name}.yaml")
        reg.refresh(force=True)
        return Response({"ok": True, "protocols": _status_with_meta()})


class ProtocolValidateView(APIView):
    """Valide un YAML sans l'enregistrer et, si un hexa d'essai est fourni, le décode."""

    def post(self, request):
        try:
            spec = parse_protocol(request.data.get("yaml", ""))
        except ProtocolError as exc:
            return Response({"ok": False, "errors": exc.errors})
        result = {"ok": True, "errors": [], "name": spec.name}
        sample = re.sub(r"\s+", "", request.data.get("hex", "") or "")
        if sample:
            try:
                raw = bytes.fromhex(sample)
            except ValueError:
                result["sample_error"] = "hexadécimal invalide"
            else:
                d = decode(spec, raw)
                result["decoded"] = {
                    "status": d.status, "issues": [i.message for i in d.issues],
                    "fields": [{"name": f.name, "value": f.value, "label": f.label, "issue": f.issue}
                               for f in d.fields],
                    "crc": None if d.crc is None else {"read": d.crc.read, "computed": d.crc.computed,
                                                        "ok": d.crc.ok},
                }
        return Response(result)
