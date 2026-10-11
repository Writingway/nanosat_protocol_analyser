"""Description d'un protocole lue depuis un fichier YAML, et sa validation.

La validation se fait en deux temps :
1. la forme (types, clés connues, bornes) — pydantic ;
2. la cohérence (champs qui se chevauchent, en-tête plus long que la frame
   minimale, colonnes inconnues…) — fonction `_coherence_errors`.

Toutes les erreurs sont renvoyées en français, avec le chemin de la clé fautive,
pour qu'un non-développeur puisse corriger son fichier.
"""
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from .crc import CRC_ALGORITHMS


class ProtocolError(Exception):
    """YAML de protocole invalide. `errors` = liste de messages lisibles."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


def _hex_int(value):
    """Accepte aussi "0x2A" écrit entre guillemets."""
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return value
    return value


HexInt = Annotated[int, BeforeValidator(_hex_int)]
ByteOrder = Literal["big", "little"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FieldSpec(_Strict):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    offset: int = Field(ge=0)
    size: int = Field(ge=1, le=8)
    byte_order: ByteOrder | None = None  # défaut : celui du protocole
    display: Literal["hex", "dec"] = "hex"
    description: str = ""
    values: dict[HexInt, str] = {}  # libellés affichés (ex. 0x11: PC)
    expect: HexInt | None = None  # valeur imposée (ex. mot de synchro)

    @property
    def end(self) -> int:
        return self.offset + self.size


class PayloadSpec(_Strict):
    offset: int = Field(ge=0)
    end: int = Field(default=0, le=0)  # compté depuis la fin de frame ; 0 = jusqu'au bout


class CrcSpec(_Strict):
    type: Literal[tuple(CRC_ALGORITHMS)]  # type: ignore[valid-type]
    offset: int = Field(le=-1)  # position du CRC comptée depuis la fin (ex. -2)
    byte_order: ByteOrder = "big"
    from_: int = Field(default=0, ge=0, alias="from")  # début de la zone couverte
    to: int | None = Field(default=None, le=0)  # fin (exclue), depuis la fin ; défaut = début du CRC
    check: bool = True  # False = CRC affiché mais pas vérifié

    @property
    def size(self) -> int:
        return CRC_ALGORITHMS[self.type].size

    @property
    def covers_to(self) -> int:
        return self.offset if self.to is None else self.to


class LengthSpec(_Strict):
    field: str
    counts: Literal["payload", "frame"] = "payload"  # ce que la valeur du champ compte
    adjust: int = 0  # valeur ajoutée au champ avant comparaison


class ProtocolSpec(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = ""
    description: str = ""
    framing: Literal["slip", "none"] = "none"
    byte_order: ByteOrder = "big"
    min_length: int = Field(ge=1)
    max_length: int = Field(ge=1, le=65535)
    fields: list[FieldSpec] = Field(min_length=1)
    payload: PayloadSpec | None = None
    crc: CrcSpec | None = None
    length: LengthSpec | None = None
    columns: list[str] | None = None

    def model_post_init(self, _context) -> None:
        if not self.label:
            self.label = self.name
        if self.columns is None:
            self.columns = [f.name for f in self.fields]

    def field(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def header_end(self) -> int:
        return max(f.end for f in self.fields)


# --- Traduction des erreurs pydantic -------------------------------------------------

_MESSAGES = {
    "missing": "clé obligatoire manquante",
    "extra_forbidden": "clé inconnue (faute de frappe ?)",
    "int_parsing": "doit être un entier (ex. 3 ou 0x2A)",
    "int_type": "doit être un entier (ex. 3 ou 0x2A)",
    "int_from_float": "doit être un entier, pas un nombre à virgule",
    "string_type": "doit être un texte",
    "list_type": "doit être une liste",
    "dict_type": "doit être un dictionnaire (clé: valeur)",
    "model_type": "doit être un dictionnaire (clé: valeur)",
    "model_attributes_type": "doit être un dictionnaire (clé: valeur)",
    "bool_parsing": "doit être true ou false",
    "bool_type": "doit être true ou false",
}


def _path(loc: tuple) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += ("." if out else "") + ("from" if part == "from_" else str(part))
    return out or "(racine)"


def _translate(err: dict) -> str:
    kind, ctx = err["type"], err.get("ctx", {})
    path = _path(err["loc"])
    if kind in _MESSAGES:
        msg = _MESSAGES[kind]
    elif kind == "greater_than_equal":
        msg = f"doit être ≥ {ctx['ge']}"
    elif kind == "less_than_equal":
        msg = f"doit être ≤ {ctx['le']}"
    elif kind == "literal_error":
        msg = f"valeur non autorisée ; choix possibles : {ctx['expected']}"
    elif kind == "too_short":
        msg = f"doit contenir au moins {ctx.get('min_length', 1)} élément(s)"
    elif kind == "string_pattern_mismatch":
        msg = ("nom invalide : minuscules, chiffres, - ou _, commençant par une lettre"
               if path == "name" else "nom invalide : lettres, chiffres ou _, sans espace")
    else:
        msg = err["msg"]
    return f"{path} : {msg}"


# --- Cohérence -----------------------------------------------------------------------

def _coherence_errors(spec: ProtocolSpec) -> list[str]:
    errors: list[str] = []

    names = [f.name for f in spec.fields]
    for n in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"fields : le champ {n} est défini en double")

    ordered = sorted(spec.fields, key=lambda f: f.offset)
    for a, b in zip(ordered, ordered[1:], strict=False):
        if b.offset < a.end:
            errors.append(f"fields : {b.name} (offset {b.offset}) chevauche {a.name} "
                          f"(octets {a.offset} à {a.end - 1})")

    for f in spec.fields:
        limit = 1 << (8 * f.size)
        for v in f.values:
            if not 0 <= v < limit:
                errors.append(f"fields.{f.name}.values : {v:#x} ne tient pas sur {f.size} octet(s)")
        if f.expect is not None and not 0 <= f.expect < limit:
            errors.append(f"fields.{f.name}.expect : {f.expect:#x} ne tient pas sur {f.size} octet(s)")

    trailer = -spec.crc.offset if spec.crc else 0
    if spec.min_length < spec.header_end + trailer:
        errors.append(f"min_length : vaut {spec.min_length} mais l'en-tête ({spec.header_end} octets)"
                      f" + le CRC ({trailer} octets) demandent au moins {spec.header_end + trailer}")
    if spec.max_length < spec.min_length:
        errors.append(f"max_length : ({spec.max_length}) est plus petit que min_length ({spec.min_length})")

    if spec.crc:
        if -spec.crc.offset < spec.crc.size:
            errors.append(f"crc.offset : un {spec.crc.type} fait {spec.crc.size} octet(s), "
                          f"l'offset doit valoir au plus -{spec.crc.size}")
        if spec.crc.covers_to > spec.crc.offset:
            errors.append("crc.to : la zone couverte ne peut pas inclure le CRC lui-même")

    if spec.payload:
        if spec.payload.offset < spec.header_end:
            errors.append(f"payload.offset : ({spec.payload.offset}) tombe dans l'en-tête "
                          f"(qui finit à l'octet {spec.header_end - 1})")
        if spec.crc and spec.payload.end > spec.crc.offset:
            errors.append(f"payload.end : ({spec.payload.end}) recouvre le CRC "
                          f"(offset {spec.crc.offset}) ; utilisez end: {spec.crc.offset}")

    for col in spec.columns or []:
        if spec.field(col) is None:
            errors.append(f"columns : le champ {col} n'existe pas dans fields")

    if spec.length and spec.field(spec.length.field) is None:
        errors.append(f"length.field : le champ {spec.length.field} n'existe pas dans fields")

    return errors


def parse_protocol(text: str) -> ProtocolSpec:
    """Texte YAML → ProtocolSpec validé. Lève ProtocolError avec la liste des problèmes."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"ligne {mark.line + 1}, colonne {mark.column + 1} : " if mark else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ProtocolError([f"syntaxe YAML : {where}{problem}"]) from None
    if not isinstance(data, dict):
        raise ProtocolError(["le fichier doit être un dictionnaire (name:, fields:, …)"])
    try:
        spec = ProtocolSpec.model_validate(data)
    except ValidationError as exc:
        raise ProtocolError([_translate(e) for e in exc.errors()]) from None
    errors = _coherence_errors(spec)
    if errors:
        raise ProtocolError(errors)
    return spec
