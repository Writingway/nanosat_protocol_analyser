"""Filtres de la liste des frames, communs à la liste et aux exports.

Paramètres d'URL acceptés :
    capture=12                      (obligatoire)
    source=3,4                      ids de sources
    direction=in | out
    status=crc_error,too_short      ou status=errors (tout sauf ok)
    from=2026-10-07T09:00:00Z       to=...
    f.DST=0x2A,0x11                 valeur d'un champ d'en-tête (hexa ou décimal), plusieurs = OU
"""
import re
from datetime import datetime

from django.db.models import Q, QuerySet
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from protocols.engine.decoder import STATUSES

from ..models import Frame

_FIELD_PARAM = re.compile(r"^f\.([A-Za-z_][A-Za-z0-9_]*)$")


def _int_list(value: str, what: str) -> list[int]:
    try:
        return [int(v.strip(), 0) for v in value.split(",") if v.strip()]
    except ValueError:
        msg = f"« {value} » : entiers attendus (ex. 42 ou 0x2A), séparés par des virgules"
        raise ValidationError({what: msg}) from None


def _date(value: str, what: str) -> datetime:
    dt = parse_datetime(value)
    if dt is None:
        raise ValidationError({what: f"« {value} » : date ISO attendue (ex. 2026-10-07T09:00:00Z)"})
    return dt


def filter_frames(params) -> QuerySet[Frame]:
    if "capture" not in params:
        raise ValidationError({"capture": "paramètre obligatoire"})
    qs = Frame.objects.filter(capture_id=_int_list(params["capture"], "capture")[0])

    if params.get("source"):
        qs = qs.filter(source_id__in=_int_list(params["source"], "source"))

    if direction := params.get("direction"):
        if direction not in ("in", "out"):
            raise ValidationError({"direction": "in ou out"})
        qs = qs.filter(direction=direction)

    if status := params.get("status"):
        if status == "errors":
            qs = qs.exclude(status="ok")
        else:
            wanted = [s.strip() for s in status.split(",") if s.strip()]
            unknown = set(wanted) - set(STATUSES)
            if unknown:
                raise ValidationError({"status": f"inconnu(s) : {', '.join(sorted(unknown))}"})
            qs = qs.filter(status__in=wanted)

    if params.get("from"):
        qs = qs.filter(ts__gte=_date(params["from"], "from"))
    if params.get("to"):
        qs = qs.filter(ts__lte=_date(params["to"], "to"))

    for key, value in params.items():
        m = _FIELD_PARAM.match(key)
        if m and value:
            name = m.group(1)
            cond = Q()
            for v in _int_list(value, key):
                cond |= Q(fields__contains={name: v})  # utilise l'index GIN
            qs = qs.filter(cond)

    return qs.order_by("ts", "id")
