"""Configuration de la capture live et lecture des topics MQTT."""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from protocols.engine.schema import ProtocolError, _translate


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrokerConfig(_Strict):
    host: str = "localhost"
    port: int = Field(default=1883, ge=1, le=65535)
    client_id: str = "analyseur-ingest"
    keepalive: int = Field(default=30, ge=5)


class IngestConfig(_Strict):
    broker: BrokerConfig = BrokerConfig()
    subscribe: list[str] = Field(min_length=1)
    topics: list[str] = Field(min_length=1)
    equipments: dict[str, str] = {}

    @field_validator("topics")
    @classmethod
    def _topics_have_direction(cls, motifs: list[str]) -> list[str]:
        for m in motifs:
            if "{direction}" not in m or "{equipment}" not in m:
                raise ValueError(f"« {m} » doit contenir {{equipment}} et {{direction}}")
        return motifs


def load_config(path: Path) -> IngestConfig:
    try:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ProtocolError([f"{path} : {exc}"]) from None
    try:
        return IngestConfig.model_validate(data or {})
    except ValidationError as exc:
        raise ProtocolError([f"{Path(path).name} › {_translate(e)}" for e in exc.errors()]) from None


@dataclass(frozen=True)
class TopicInfo:
    bench: str
    equipment: str
    direction: str  # "in" ou "out"


def _compile(motif: str) -> re.Pattern:
    """« {bench}/{equipment}/serial/{direction} » → regex à groupes nommés."""
    out, pos = "", 0
    for m in re.finditer(r"\{(bench|equipment|direction)\}", motif):
        out += re.escape(motif[pos:m.start()])
        out += "(?P<direction>in|out)" if m.group(1) == "direction" else f"(?P<{m.group(1)}>[^/]+)"
        pos = m.end()
    return re.compile(out + re.escape(motif[pos:]) + "$")


class TopicMatcher:
    def __init__(self, motifs: list[str]):
        self._patterns = [_compile(m) for m in motifs]

    def match(self, topic: str) -> TopicInfo | None:
        for p in self._patterns:
            m = p.match(topic)
            if m:
                g = m.groupdict()
                return TopicInfo(g.get("bench") or "", g["equipment"], g["direction"])
        return None
