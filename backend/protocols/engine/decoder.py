"""Décodage de l'en-tête d'une frame à partir de sa description (ProtocolSpec).

Règles :
- ne lève jamais d'exception sur des octets reçus, quels qu'ils soient ;
- décode fidèlement : un champ présent est toujours lu, même si la frame est fausse ;
- chaque anomalie devient une `Issue` ; le statut de la frame est la plus grave.
"""
from dataclasses import dataclass, field

from .crc import compute_crc
from .framing import deframe
from .schema import ProtocolSpec

# Statuts, du plus grave au moins grave. Le statut d'une frame = sa première anomalie dans cet ordre.
STATUSES = (
    "malformed_line",  # ligne de log illisible (attribué par le lecteur de logs)
    "unknown_protocol",  # aucun protocole chargé pour cette source (attribué par l'ingestion)
    "empty",
    "too_long",
    "framing_error",
    "too_short",
    "header_mismatch",
    "length_mismatch",
    "crc_error",
    "ok",
)
SEVERITY = {s: i for i, s in enumerate(STATUSES)}


@dataclass
class Issue:
    code: str
    message: str


@dataclass
class DecodedField:
    name: str
    offset: int
    size: int
    value: int | None  # None si la frame est trop courte pour contenir le champ
    display: str = "hex"
    label: str | None = None
    description: str = ""
    issue: str | None = None


@dataclass
class CrcInfo:
    offset: int
    size: int
    read: int
    computed: int
    ok: bool | None  # None = vérification désactivée dans le YAML
    covers: tuple[int, int]  # (début, fin exclue) dans la frame déframée


@dataclass
class DecodedFrame:
    status: str
    data: bytes  # octets après déframing
    positions: list[int]  # data[i] provient de raw[positions[i]]
    issues: list[Issue] = field(default_factory=list)
    fields: list[DecodedField] = field(default_factory=list)
    payload: tuple[int, int] | None = None  # (offset, taille)
    crc: CrcInfo | None = None

    def values(self) -> dict[str, int]:
        """Valeurs des champs lus — c'est ce qui est indexé en base pour les filtres."""
        return {f.name: f.value for f in self.fields if f.value is not None}

    @property
    def detail(self) -> str:
        return " ; ".join(i.message for i in self.issues)


def worst_status(codes) -> str:
    return min(codes, key=SEVERITY.__getitem__, default="ok")


def _read_int(data: bytes, offset: int, size: int, order: str) -> int:
    return int.from_bytes(data[offset:offset + size], order)  # type: ignore[arg-type]


def decode(spec: ProtocolSpec, raw: bytes) -> DecodedFrame:
    issues: list[Issue] = []

    # Garde-fou avant tout travail : une frame SLIP fait au pire 2*max + 2 octets bruts.
    raw_limit = spec.max_length * 2 + 2 if spec.framing == "slip" else spec.max_length
    if len(raw) > raw_limit:
        msg = f"{len(raw)} octets bruts, maximum {spec.max_length} pour {spec.name} : frame non décodée"
        return DecodedFrame("too_long", b"", [], [Issue("too_long", msg)])

    framed = deframe(raw, spec.framing)
    data = framed.data
    issues += [Issue("framing_error", m) for m in framed.issues]

    if not data:
        issues.insert(0, Issue("empty", "frame vide"))
        return DecodedFrame(worst_status(i.code for i in issues), data, framed.positions, issues)

    if len(data) > spec.max_length:
        issues.insert(0, Issue("too_long", f"{len(data)} octets, maximum {spec.max_length} : non décodée"))
        return DecodedFrame("too_long", data, framed.positions, issues)

    if len(data) < spec.min_length:
        issues.append(Issue("too_short", f"{len(data)} octets, minimum {spec.min_length}"))

    # --- Champs de l'en-tête ---
    fields: list[DecodedField] = []
    for f in spec.fields:
        df = DecodedField(f.name, f.offset, f.size, None, f.display, description=f.description)
        if f.end <= len(data):
            df.value = _read_int(data, f.offset, f.size, f.byte_order or spec.byte_order)
            df.label = f.values.get(df.value)
            if f.expect is not None and df.value != f.expect:
                df.issue = f"attendu {f.expect:#0{2 + 2 * f.size}x}"
                issues.append(Issue("header_mismatch",
                                    f"{f.name} = {df.value:#0{2 + 2 * f.size}x}, {df.issue}"))
        fields.append(df)

    result = DecodedFrame("ok", data, framed.positions, issues, fields)

    # La suite (DATA, longueur, CRC) n'a de sens que si la frame a sa taille minimale.
    if len(data) < spec.min_length:
        result.status = worst_status(i.code for i in issues)
        return result

    n = len(data)
    trailer_start = n + spec.crc.offset if spec.crc else n

    if spec.payload:
        start = spec.payload.offset
        stop = n + spec.payload.end
        result.payload = (start, max(0, stop - start))

    if spec.length:
        lf = spec.field(spec.length.field)
        declared = result.values().get(lf.name) if lf else None
        if declared is not None:
            actual = result.payload[1] if spec.length.counts == "payload" and result.payload else n
            expected = declared + spec.length.adjust
            if expected != actual:
                what = "DATA" if spec.length.counts == "payload" else "frame"
                issues.append(Issue("length_mismatch",
                                    f"{lf.name} annonce {expected} octets, {what} en contient {actual}"))

    if spec.crc:
        c = spec.crc
        read = _read_int(data, trailer_start, c.size, c.byte_order)
        covers = (c.from_, n + c.covers_to)
        computed = compute_crc(c.type, data[covers[0]:covers[1]])
        ok = (read == computed) if c.check else None
        result.crc = CrcInfo(trailer_start, c.size, read, computed, ok, covers)
        if ok is False:
            width = 2 + 2 * c.size
            issues.append(Issue("crc_error", f"CRC lu {read:#0{width}x}, calculé {computed:#0{width}x}"))

    result.status = worst_status(i.code for i in issues)
    return result
