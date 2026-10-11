"""Boucle de la capture live, séparée du client MQTT pour être testable sans broker.

Organisation des threads :
- le thread réseau de paho ne fait QUE déposer dans une file (messages et événements de connexion) :
  il rend la main immédiatement, le broker ne voit jamais un abonné lent ;
- le thread principal (`run_once` en boucle) est le seul à parler à la base.
"""
import logging
import queue
import time
from dataclasses import dataclass
from datetime import datetime

from django.db import close_old_connections, connection
from django.utils import timezone

from .ingest import Ingestor, notify
from .live import IngestConfig, TopicMatcher
from .models import Capture, CaptureEvent, LiveControl, Source

log = logging.getLogger(__name__)


@dataclass
class Message:
    topic: str
    payload: bytes
    received_at: datetime


@dataclass
class ConnectionEvent:
    connected: bool
    reason: str
    at: datetime


class LiveIngester:
    CONTROL_PERIOD = 0.5  # relecture de LiveControl (démarrer / arrêter depuis l'IHM)
    FLUSH_PERIOD = 0.2  # écriture du lot même s'il n'est pas plein
    HEARTBEAT_PERIOD = 2.0
    STATS_PERIOD = 1.0
    BATCH_SIZE = 500

    def __init__(self, config: IngestConfig):
        self.config = config
        self.matcher = TopicMatcher(config.topics)
        self.inbox: queue.Queue = queue.Queue()
        self.capture_id: int | None = None
        self.ingestor: Ingestor | None = None
        self._sources: dict[str, Source] = {}
        self._unknown_topics: set[str] = set()
        now = time.monotonic()
        self._next_control = self._next_flush = self._next_heartbeat = self._next_stats = now
        self._last_stats = now
        self.received = self.ignored = 0
        self._received_at_last_stats = 0

    # --- Appelés par le thread réseau : aucune opération lente ici ---------------

    def on_message(self, topic: str, payload: bytes) -> None:
        self.inbox.put(Message(topic, payload, timezone.now()))

    def on_connection(self, connected: bool, reason: str = "") -> None:
        self.inbox.put(ConnectionEvent(connected, reason, timezone.now()))

    # --- Thread principal ----------------------------------------------------------

    def run_once(self, timeout: float = 0.1) -> None:
        """Traite ce qui est dans la file (au plus ~timeout s d'attente), puis les tâches périodiques."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            try:
                item = self.inbox.get(timeout=max(0.0, remaining)) if remaining > 0 else self.inbox.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, Message):
                self._handle_message(item)
            else:
                self._handle_connection(item)
        self._periodic()

    def shutdown(self) -> None:
        if self.ingestor:
            self.ingestor.flush()
        ctl = LiveControl.get()
        ctl.connected, ctl.heartbeat, ctl.since = False, None, timezone.now()
        ctl.save(update_fields=["connected", "heartbeat", "since"])
        notify({"type": "live"})

    # --- Détails -----------------------------------------------------------------

    def _handle_message(self, msg: Message) -> None:
        self.received += 1
        if self.ingestor is None:
            self.ignored += 1  # aucune capture en cours : on écoute mais on n'enregistre pas
            return
        source = self._source_for(msg.topic)
        if source is None:
            self.ignored += 1
            return
        direction = self.matcher.match(msg.topic).direction
        self.ingestor.add(msg.payload.decode("utf-8", errors="replace"), source, direction, msg.received_at)

    def _source_for(self, topic: str) -> Source | None:
        src = self._sources.get(topic)
        if src is not None:
            return src
        info = self.matcher.match(topic)
        if info is None:
            if topic not in self._unknown_topics:
                self._unknown_topics.add(topic)
                log.warning("Topic %s ignoré : aucun motif de config/ingest.yaml ne correspond", topic)
            return None
        # Équipement absent de la config → protocole vide : les frames seront « unknown_protocol ».
        protocol = self.config.equipments.get(info.equipment, "")
        src, _ = Source.objects.get_or_create(
            kind=Source.Kind.MQTT, name=topic, bench=info.bench, equipment=info.equipment,
            defaults={"protocol": protocol},
        )
        if src.protocol != protocol:
            src.protocol = protocol
            src.save(update_fields=["protocol"])
        self._sources[topic] = src
        return src

    def _handle_connection(self, ev: ConnectionEvent) -> None:
        ctl = LiveControl.get()
        ctl.connected, ctl.since = ev.connected, ev.at
        ctl.last_error = "" if ev.connected else ev.reason[:500]
        ctl.save(update_fields=["connected", "since", "last_error"])
        if self.capture_id:
            kind = CaptureEvent.Kind.CONNECTED if ev.connected else CaptureEvent.Kind.DISCONNECTED
            CaptureEvent.objects.create(capture_id=self.capture_id, ts=ev.at, kind=kind, message=ev.reason[:500])
        log.info("Broker %s %s", "connecté" if ev.connected else "déconnecté", ev.reason)
        notify({"type": "live"})

    def _periodic(self) -> None:
        now = time.monotonic()
        if now >= self._next_control:
            self._next_control = now + self.CONTROL_PERIOD
            self._sync_control()
        if self.ingestor and now >= self._next_flush:
            self._next_flush = now + self.FLUSH_PERIOD
            self.ingestor.flush()
        if now >= self._next_heartbeat:
            self._next_heartbeat = now + self.HEARTBEAT_PERIOD
            LiveControl.objects.filter(pk=1).update(heartbeat=timezone.now())
            if not connection.in_atomic_block:
                close_old_connections()  # process de longue durée : on recycle les connexions mortes
        if now >= self._next_stats:
            elapsed = max(now - self._last_stats, 1e-3)
            rate = (self.received - self._received_at_last_stats) / elapsed
            self._received_at_last_stats, self._last_stats = self.received, now
            self._next_stats = now + self.STATS_PERIOD
            notify({"type": "stats", "rate": round(rate, 1), "queue": self.inbox.qsize(),
                    "received": self.received, "ignored": self.ignored,
                    "capture": self.capture_id, "written": self.ingestor.total if self.ingestor else 0})

    def _sync_control(self) -> None:
        """Suit la capture demandée par l'IHM (LiveControl.capture)."""
        ctl = LiveControl.get()
        wanted = ctl.capture_id if ctl.requested else None
        if wanted == self.capture_id:
            return
        if self.ingestor:
            self.ingestor.flush()
            log.info("Capture %s : fin d'enregistrement (%s frames)", self.capture_id, self.ingestor.total)
        self.capture_id, self.ingestor = wanted, None
        if wanted:
            capture = Capture.objects.filter(pk=wanted).first()
            if capture:
                self.ingestor = Ingestor(capture, batch_size=self.BATCH_SIZE)
                log.info("Capture %s « %s » : enregistrement démarré", capture.pk, capture.name)
