"""Lecture d'une ligne de log du banc (même format pour les fichiers et les messages MQTT).

    temps | date_emission | date_reception | data=<octets en hexa>

Une ligne illisible ne lève jamais d'exception : elle est renvoyée avec `error` renseigné
et ses octets d'origine, pour être enregistrée et signalée (statut malformed_line).
"""
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

# Au-delà, la ligne est tronquée avant stockage (une frame valide est bien plus courte).
MAX_LINE_BYTES = 64 * 1024

_DATA_RE = re.compile(r"data=([^|]*)")
_WS_RE = re.compile(r"\s+")


@dataclass
class LogLine:
    raw: bytes  # octets de la frame (ou la ligne elle-même si illisible)
    ts_emit: datetime | None = None
    ts_bench_rx: datetime | None = None
    error: str | None = None


def _parse_date(text: str, tz: ZoneInfo) -> datetime | None:
    try:
        dt = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def parse_line(text: str, tz: ZoneInfo) -> LogLine | None:
    """Renvoie None pour une ligne blanche (ce n'est pas une frame)."""
    text = text.rstrip("\r\n")
    if not text.strip():
        return None

    truncated = len(text) > MAX_LINE_BYTES
    if truncated:
        text = text[:MAX_LINE_BYTES]

    parts = text.split("|")
    ts_emit = _parse_date(parts[1], tz) if len(parts) > 1 else None
    ts_rx = _parse_date(parts[2], tz) if len(parts) > 2 else None

    m = _DATA_RE.search(text)
    if not m:
        return LogLine(text.encode(errors="replace"), ts_emit, ts_rx, "ligne hors format (pas de « data= »)")
    hexa = _WS_RE.sub("", m.group(1))
    if truncated:
        return LogLine(text.encode(errors="replace"), ts_emit, ts_rx,
                       f"ligne de plus de {MAX_LINE_BYTES} caractères, tronquée")
    try:
        raw = bytes.fromhex(hexa)
    except ValueError:
        return LogLine(text.encode(errors="replace"), ts_emit, ts_rx, "data= ne contient pas de l'hexadécimal valide")
    return LogLine(raw, ts_emit, ts_rx)
