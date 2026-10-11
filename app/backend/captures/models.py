from django.contrib.postgres.indexes import GinIndex
from django.db import models

from protocols.engine.decoder import STATUSES


class Source(models.Model):
    """D'où viennent les frames : un topic MQTT ou un fichier, rattaché à un équipement."""

    class Kind(models.TextChoices):
        FILE = "file", "Fichier"
        MQTT = "mqtt", "MQTT"

    kind = models.CharField(max_length=4, choices=Kind.choices)
    name = models.CharField(max_length=255)  # topic MQTT ou nom du fichier
    bench = models.CharField(max_length=100, blank=True)  # banc de test (ou IP)
    equipment = models.CharField(max_length=100)
    protocol = models.CharField(max_length=50)  # nom du protocole YAML
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "name", "bench", "equipment"], name="uniq_source"),
        ]

    def __str__(self) -> str:
        where = f"{self.bench}/" if self.bench else ""
        return f"{where}{self.equipment} ({self.name})"


class Capture(models.Model):
    """Une session : un import de fichiers, ou une capture live entre Démarrer et Arrêter."""

    class Kind(models.TextChoices):
        IMPORT = "import", "Import de fichiers"
        LIVE = "live", "Capture live"

    class State(models.TextChoices):
        LIVE = "live", "En cours"
        ENDED = "ended", "Terminée"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=6, choices=Kind.choices)
    state = models.CharField(max_length=5, choices=State.choices, default=State.ENDED)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    # Empreinte des fichiers importés : détecte le ré-import du même fichier.
    file_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    # Compteur tenu à jour à chaque lot écrit : évite un COUNT(*) sur des millions de lignes
    # pour afficher la liste des captures.
    frame_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return self.name


class CaptureEvent(models.Model):
    """Événement notable pendant une capture live (coupure / reprise du broker…)."""

    class Kind(models.TextChoices):
        DISCONNECTED = "disconnected", "Broker déconnecté"
        CONNECTED = "connected", "Broker connecté"

    capture = models.ForeignKey(Capture, on_delete=models.CASCADE, related_name="events")
    ts = models.DateTimeField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["ts"]


class Frame(models.Model):
    class Direction(models.TextChoices):
        IN = "in", "Demande (in)"
        OUT = "out", "Réponse (out)"

    capture = models.ForeignKey(Capture, on_delete=models.CASCADE, related_name="frames")
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="frames")
    # Version du YAML utilisée pour décoder (null si aucun protocole n'était chargé).
    protocol_version = models.ForeignKey(
        "protocols.ProtocolVersion", on_delete=models.PROTECT, null=True, related_name="frames"
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    # Horodatage de référence = date d'émission écrite par le banc (UTC).
    ts = models.DateTimeField()
    ts_bench_rx = models.DateTimeField(null=True, blank=True)  # date de réception notée par le banc
    received_at = models.DateTimeField()  # date de réception par l'analyseur
    # Octets tels que reçus (avec SLIP). Pour une ligne illisible : la ligne elle-même.
    raw = models.BinaryField()
    status = models.CharField(max_length=20, choices=[(s, s) for s in STATUSES])
    detail = models.TextField(blank=True)
    # Valeurs des champs d'en-tête (ex. {"DST": 42}), calculées avec `protocol_version`.
    # Dérivées des octets bruts mais stockées pour pouvoir filtrer en SQL.
    fields = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["capture", "ts", "id"], name="frame_capture_ts"),
            models.Index(fields=["capture", "status"], name="frame_capture_status"),
            GinIndex(fields=["fields"], name="frame_fields_gin", opclasses=["jsonb_path_ops"]),
        ]


class LiveControl(models.Model):
    """Ligne unique : pilotage de la capture live depuis l'IHM, et état du broker vu par l'ingester."""

    requested = models.BooleanField(default=False)  # l'utilisateur veut capturer
    capture = models.ForeignKey(Capture, null=True, blank=True, on_delete=models.SET_NULL)
    connected = models.BooleanField(default=False)
    since = models.DateTimeField(null=True, blank=True)  # depuis quand l'état `connected` dure
    last_error = models.CharField(max_length=500, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)  # dernier signe de vie de l'ingester

    @classmethod
    def get(cls) -> "LiveControl":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
