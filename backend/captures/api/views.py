from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from protocols.registry import get_registry

from ..importer import DuplicateImport, LogFile, guess_direction, import_logs
from ..models import Capture, Frame, Source
from . import export
from .filters import filter_frames
from .serializers import capture_detail_json, capture_json, frame_detail_json, frame_json, source_json

MAX_PAGE = 1000


class CaptureListView(APIView):
    parser_classes = [MultiPartParser]

    def get(self, request):
        return Response([capture_json(c) for c in Capture.objects.all()[:500]])

    def post(self, request):
        """Import de fichiers : file_in / file_out, ou files (sens déduit du nom)."""
        data = request.data
        errors = {}
        equipment = (data.get("equipment") or "").strip()
        protocol = (data.get("protocol") or "").strip()
        if not equipment:
            errors["equipment"] = "obligatoire"
        if not protocol:
            errors["protocol"] = "obligatoire"
        elif get_registry().get(protocol) is None:
            available = ", ".join(sorted(get_registry().all())) or "aucun"
            errors["protocol"] = f"protocole « {protocol} » non chargé (disponibles : {available})"

        files = []
        for key, direction in (("file_in", "in"), ("file_out", "out")):
            if key in request.FILES:
                files.append((request.FILES[key], direction))
        for f in request.FILES.getlist("files"):
            direction = guess_direction(f.name)
            if direction is None:
                errors["files"] = f"{f.name} : sens in/out indéterminable, utilisez file_in / file_out"
            files.append((f, direction))
        if not files:
            errors["files"] = "au moins un fichier est nécessaire"
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            capture = import_logs(
                [LogFile(f.name, f, d) for f, d in files],
                equipment=equipment, protocol=protocol, bench=(data.get("bench") or "").strip(),
                name=(data.get("name") or "").strip() or None, force=data.get("force") in ("1", "true"),
            )
        except DuplicateImport as exc:
            return Response({"detail": str(exc), "capture": exc.capture.pk}, status=status.HTTP_409_CONFLICT)
        return Response(capture_detail_json(capture), status=status.HTTP_201_CREATED)


class CaptureDetailView(APIView):
    def get(self, request, pk):
        return Response(capture_detail_json(get_object_or_404(Capture, pk=pk)))

    def delete(self, request, pk):
        capture = get_object_or_404(Capture, pk=pk)
        if capture.state == Capture.State.LIVE:
            return Response({"detail": "Arrêtez la capture live avant de la supprimer."},
                            status=status.HTTP_409_CONFLICT)
        try:
            capture.delete()
        except ProtectedError:
            return Response({"detail": "Suppression impossible."}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CaptureExportView(APIView):
    def get(self, request, pk):
        capture = get_object_or_404(Capture, pk=pk)
        params = request.query_params.copy()
        params["capture"] = str(pk)
        qs = filter_frames(params)
        fmt = request.query_params.get("format", "csv")
        if fmt == "log":
            return export.export_log(capture, qs, request.query_params.get("direction"))
        if fmt == "csv":
            versions = capture.frames.order_by().values_list("protocol_version_id", flat=True).distinct()
            return export.export_csv(capture, qs, export.field_names_of([v for v in versions if v]))
        return Response({"format": "csv ou log"}, status=status.HTTP_400_BAD_REQUEST)


class FrameListView(APIView):
    def get(self, request):
        qs = filter_frames(request.query_params)
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
            limit = min(MAX_PAGE, max(1, int(request.query_params.get("limit", 200))))
        except ValueError:
            return Response({"detail": "offset et limit doivent être des entiers"}, status=400)
        page = list(qs[offset:offset + limit])
        return Response({"count": qs.count(), "offset": offset, "results": [frame_json(f) for f in page]})


class FrameIndexView(APIView):
    """Position d'une frame dans la liste filtrée (pour y faire défiler l'IHM)."""

    def get(self, request, pk):
        frame = get_object_or_404(Frame, pk=pk)
        qs = filter_frames(request.query_params)
        before = qs.filter(ts__lt=frame.ts).count() + qs.filter(ts=frame.ts, id__lt=frame.id).count()
        return Response({"index": before})


class FrameDetailView(APIView):
    def get(self, request, pk):
        return Response(frame_detail_json(get_object_or_404(Frame, pk=pk)))


class SourceListView(APIView):
    def get(self, request):
        return Response([source_json(s) for s in Source.objects.order_by("bench", "equipment", "name")])
