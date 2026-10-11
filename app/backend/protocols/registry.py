"""Registre des protocoles chargés depuis le dossier YAML, avec rechargement à chaud.

Fonctionnement :
- à chaque accès (au plus toutes les POLL_INTERVAL secondes), on compare la date de
  modification des fichiers *.yaml du dossier avec celle déjà vue ;
- un fichier modifié est relu et validé ENTIÈREMENT avant d'être pris en compte ;
- s'il est invalide, l'ancienne version reste active et l'erreur est conservée
  pour être affichée dans l'IHM.

Pas de thread ni d'inotify : simple, et fonctionne aussi sur des dossiers montés (WSL, réseau).
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from .engine.schema import ProtocolError, ProtocolSpec, parse_protocol

log = logging.getLogger(__name__)

POLL_INTERVAL = 2.0


@dataclass(frozen=True)
class LoadedProtocol:
    spec: ProtocolSpec
    text: str
    sha256: str
    path: Path


@dataclass
class FileState:
    mtime: float
    errors: list[str] = field(default_factory=list)
    name: str | None = None  # protocole déclaré par ce fichier (s'il a déjà été valide)


class ProtocolRegistry:
    def __init__(self, directory: Path, poll_interval: float = POLL_INTERVAL):
        self.directory = Path(directory)
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self._protocols: dict[str, LoadedProtocol] = {}
        self._files: dict[Path, FileState] = {}
        self._last_check = 0.0
        self._version_ids: dict[str, int] = {}  # sha256 -> ProtocolVersion.id

    # --- Lecture ---------------------------------------------------------------

    def get(self, name: str) -> LoadedProtocol | None:
        self.refresh()
        return self._protocols.get(name)

    def all(self) -> dict[str, LoadedProtocol]:
        self.refresh()
        return dict(self._protocols)

    def status(self) -> list[dict]:
        """État de chaque fichier, pour l'API : protocole actif, version, erreurs éventuelles."""
        self.refresh()
        out = []
        with self._lock:
            for path, st in sorted(self._files.items()):
                loaded = self._protocols.get(st.name) if st.name else None
                out.append({
                    "file": path.name,
                    "name": loaded.spec.name if loaded else st.name,
                    "label": loaded.spec.label if loaded else None,
                    "description": loaded.spec.description if loaded else "",
                    "sha256": loaded.sha256 if loaded else None,
                    "active": loaded is not None,
                    "errors": list(st.errors),
                })
        return out

    # --- Rechargement ----------------------------------------------------------

    def refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_check < self.poll_interval:
            return
        with self._lock:
            self._last_check = now
            self._scan()

    def _scan(self) -> None:
        if not self.directory.is_dir():
            log.warning("Dossier des protocoles introuvable : %s", self.directory)
            return
        seen = set()
        for path in sorted(list(self.directory.glob("*.yaml")) + list(self.directory.glob("*.yml"))):
            seen.add(path)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            st = self._files.get(path)
            if st is None or st.mtime != mtime:
                self._load_file(path, mtime, st)
        # Fichiers supprimés : leur protocole n'est plus disponible pour les nouvelles frames.
        for path in set(self._files) - seen:
            st = self._files.pop(path)
            if st.name and self._protocols.get(st.name, None) and self._protocols[st.name].path == path:
                del self._protocols[st.name]
                log.info("Protocole %s retiré (fichier %s supprimé)", st.name, path.name)

    def _load_file(self, path: Path, mtime: float, previous: FileState | None) -> None:
        st = FileState(mtime=mtime, name=previous.name if previous else None)
        self._files[path] = st
        try:
            text = path.read_text(encoding="utf-8")
            spec = parse_protocol(text)
        except ProtocolError as exc:
            st.errors = exc.errors
        except (OSError, UnicodeDecodeError) as exc:
            st.errors = [f"lecture impossible : {exc}"]
        else:
            other = self._protocols.get(spec.name)
            if spec.name != path.stem:
                st.errors = [f"name : vaut « {spec.name} » mais le fichier s'appelle {path.name} ; "
                             f"ils doivent correspondre ({spec.name}.yaml)"]
            elif other and other.path != path:
                st.errors = [f"name : le protocole {spec.name} est déjà défini dans {other.path.name}"]
            else:
                sha = hashlib.sha256(text.encode()).hexdigest()
                self._protocols[spec.name] = LoadedProtocol(spec, text, sha, path)
                st.name = spec.name
                log.info("Protocole %s chargé (%s, version %s)", spec.name, path.name, sha[:8])
                return
        kept = " — l'ancienne version reste active" if st.name in self._protocols else ""
        log.warning("Protocole %s invalide%s : %s", path.name, kept, " | ".join(st.errors))

    # --- Lien avec la base -----------------------------------------------------

    def version_id(self, loaded: LoadedProtocol) -> int:
        """Id de la ProtocolVersion correspondant à ce texte YAML (créée au premier usage)."""
        vid = self._version_ids.get(loaded.sha256)
        if vid is None:
            from .models import ProtocolVersion

            obj, _ = ProtocolVersion.objects.get_or_create(
                sha256=loaded.sha256, defaults={"name": loaded.spec.name, "yaml_text": loaded.text}
            )
            vid = self._version_ids[loaded.sha256] = obj.id
        return vid


@lru_cache(maxsize=256)
def spec_for_version(version_id: int) -> ProtocolSpec:
    """Spec d'une version figée (pour re-décoder une ancienne frame à l'affichage)."""
    from .models import ProtocolVersion

    return parse_protocol(ProtocolVersion.objects.get(pk=version_id).yaml_text)


_registry: ProtocolRegistry | None = None


def get_registry() -> ProtocolRegistry:
    global _registry
    if _registry is None:
        _registry = ProtocolRegistry(settings.PROTOCOLS_DIR)
    return _registry
