"""Flux d'événements temps réel vers le navigateur (Server-Sent Events).

Source : les NOTIFY PostgreSQL émis par l'ingestion (canal analyseur_frames).
Le navigateur reçoit des messages légers (« 500 nouvelles frames dans la capture 12 ») et
recharge lui-même uniquement les lignes visibles : le flux ne transporte jamais les frames.
"""
import json

import psycopg
from django.conf import settings
from django.http import StreamingHttpResponse

from ..ingest import NOTIFY_CHANNEL

KEEPALIVE = 15  # secondes : évite qu'un proxy coupe une connexion silencieuse


def _conninfo() -> dict:
    db = settings.DATABASES["default"]
    return {"dbname": db["NAME"], "user": db["USER"], "password": db["PASSWORD"],
            "host": db["HOST"], "port": db["PORT"], "autocommit": True}


async def _events():
    conn = await psycopg.AsyncConnection.connect(**_conninfo())
    try:
        await conn.execute(f"LISTEN {NOTIFY_CHANNEL}")
        yield "retry: 3000\n\n"  # délai de reconnexion automatique du navigateur
        yield "event: hello\ndata: {}\n\n"
        while True:
            async for n in conn.notifies(timeout=KEEPALIVE):
                try:
                    kind = json.loads(n.payload).get("type", "message")
                except ValueError:
                    continue
                yield f"event: {kind}\ndata: {n.payload}\n\n"
            yield ": keep-alive\n\n"
    finally:
        # Exécuté aussi quand le navigateur ferme l'onglet (annulation par le serveur ASGI).
        await conn.close()


async def stream(request):
    resp = StreamingHttpResponse(_events(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"  # nginx : ne pas mettre le flux en tampon
    return resp
