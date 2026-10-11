"""Pilotage de la capture live depuis l'IHM. L'ingester (process séparé) suit LiveControl."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..ingest import notify
from ..models import Capture, LiveControl
from .serializers import capture_json

INGESTER_TIMEOUT = timedelta(seconds=6)  # 3 battements de cœur manqués


def live_state() -> dict:
    ctl = LiveControl.get()
    alive = bool(ctl.heartbeat and timezone.now() - ctl.heartbeat < INGESTER_TIMEOUT)
    capture = ctl.capture if ctl.requested and ctl.capture_id else None
    return {
        "recording": capture is not None,
        "capture": capture_json(capture) if capture else None,
        "ingester_alive": alive,
        "connected": alive and ctl.connected,
        "since": ctl.since,
        "last_error": ctl.last_error,
    }


class LiveView(APIView):
    def get(self, request):
        return Response(live_state())


class LiveStartView(APIView):
    def post(self, request):
        with transaction.atomic():
            ctl = LiveControl.objects.select_for_update().get_or_create(pk=1)[0]
            if ctl.requested and ctl.capture_id:
                return Response({"detail": "Une capture live est déjà en cours.", **live_state()},
                                status=status.HTTP_409_CONFLICT)
            now = timezone.now()
            name = (request.data.get("name") or "").strip() or f"Live {timezone.localtime(now):%d/%m/%Y %H:%M:%S}"
            capture = Capture.objects.create(name=name[:200], kind=Capture.Kind.LIVE,
                                             state=Capture.State.LIVE, started_at=now)
            ctl.requested, ctl.capture = True, capture
            ctl.save(update_fields=["requested", "capture"])
        notify({"type": "live"})
        return Response(live_state(), status=status.HTTP_201_CREATED)


class LiveStopView(APIView):
    def post(self, request):
        with transaction.atomic():
            ctl = LiveControl.objects.select_for_update().get_or_create(pk=1)[0]
            if ctl.capture_id:
                Capture.objects.filter(pk=ctl.capture_id, state=Capture.State.LIVE).update(
                    state=Capture.State.ENDED, ended_at=timezone.now())
            ctl.requested, ctl.capture = False, None
            ctl.save(update_fields=["requested", "capture"])
        notify({"type": "live"})
        return Response(live_state())
