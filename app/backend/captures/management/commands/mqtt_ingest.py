"""Process de capture live : s'abonne au broker et enregistre les frames de la capture en cours.

    python manage.py mqtt_ingest [--config ../config/ingest.yaml]

Tourne en permanence ; la capture se démarre / s'arrête depuis l'IHM.
"""
import logging
import signal

import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from captures.live import load_config
from captures.live_ingester import LiveIngester
from protocols.engine.schema import ProtocolError

log = logging.getLogger(__name__)

# Un seul service de capture à la fois : deux ingesters avec le même client_id se font
# éjecter du broker l'un l'autre en boucle (et écriraient chaque frame en double).
SINGLETON_LOCK = 0x414E4C59  # identifiant arbitraire du verrou PostgreSQL


class Command(BaseCommand):
    help = "Capture live MQTT (passive : abonnement seul, aucune publication)."

    def add_arguments(self, parser):
        parser.add_argument("--config", default=str(settings.INGEST_CONFIG))

    def handle(self, *args, **opts):
        try:
            config = load_config(opts["config"])
        except ProtocolError as exc:
            raise CommandError("Configuration invalide :\n  " + "\n  ".join(exc.errors)) from None

        with connection.cursor() as cur:
            # Verrou de session : libéré automatiquement à la fin du process, même en cas de crash.
            cur.execute("SELECT pg_try_advisory_lock(%s)", [SINGLETON_LOCK])
            if not cur.fetchone()[0]:
                raise CommandError("Un service de capture tourne déjà (make ingest / make dev). "
                                   "Arrêtez-le avant d'en lancer un autre.")

        ingester = LiveIngester(config)
        b = config.broker
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=b.client_id, clean_session=True)

        def on_connect(client, userdata, flags, reason_code, properties):
            if reason_code.is_failure:
                ingester.on_connection(False, f"connexion refusée : {reason_code}")
                return
            # (Ré)abonnement à chaque connexion : indispensable après une coupure.
            for topic in config.subscribe:
                client.subscribe(topic, qos=0)
            ingester.on_connection(True, f"{b.host}:{b.port}")

        def on_disconnect(client, userdata, flags, reason_code, properties):
            ingester.on_connection(False, f"coupure ({reason_code}) — reconnexion automatique")

        def on_message(client, userdata, msg):
            ingester.on_message(msg.topic, msg.payload)

        client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        # Réception : file illimitée côté client, le thread réseau ne bloque jamais.
        client.max_queued_messages_set(0)
        # connect_async : si le broker est absent au démarrage, paho réessaie en boucle.
        client.connect_async(b.host, b.port, keepalive=b.keepalive)
        client.loop_start()

        stop = False

        def request_stop(signum, frame):
            nonlocal stop
            stop = True

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)

        self.stdout.write(f"Capture live : broker {b.host}:{b.port}, abonnements {', '.join(config.subscribe)}")
        try:
            while not stop:
                ingester.run_once(timeout=0.1)
        finally:
            client.loop_stop()
            client.disconnect()
            ingester.shutdown()
            self.stdout.write("Arrêt de la capture live.")
