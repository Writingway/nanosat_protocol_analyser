"""Retrait de l'encapsulation (framing) avant décodage de l'en-tête.

`framing: slip` (RFC 1055) : délimiteur c0, échappements db dc → c0 et db dd → db.
`framing: none` : les octets sont la frame telle quelle.

Principe : on ne corrige rien. Une anomalie est signalée (issues) et on garde
les octets tels quels pour que l'utilisateur voie exactement ce qui a été reçu.
"""
from dataclasses import dataclass, field

SLIP_END, SLIP_ESC, SLIP_ESC_END, SLIP_ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD


@dataclass
class Deframed:
    data: bytes
    # positions[i] = index dans les octets bruts du i-ème octet décodé
    # (sert à surligner un champ dans la vue « brut » de l'IHM)
    positions: list[int]
    issues: list[str] = field(default_factory=list)


def deframe(raw: bytes, mode: str) -> Deframed:
    if mode == "slip":
        return _slip(raw)
    return Deframed(raw, list(range(len(raw))))


def _slip(raw: bytes) -> Deframed:
    issues: list[str] = []
    # Délimiteurs de début (optionnels) et de fin.
    start, end = 0, len(raw)
    while start < end and raw[start] == SLIP_END:
        start += 1
    has_end = end > start and raw[end - 1] == SLIP_END
    while end > start and raw[end - 1] == SLIP_END:
        end -= 1
    if start == end:  # rien que des c0 (ou vide)
        return Deframed(b"", [])
    if not has_end:
        issues.append("délimiteur SLIP de fin (c0) absent")

    out = bytearray()
    positions: list[int] = []
    i = start
    while i < end:
        b = raw[i]
        if b == SLIP_ESC:
            nxt = raw[i + 1] if i + 1 < end else None
            if nxt == SLIP_ESC_END:
                out.append(SLIP_END)
            elif nxt == SLIP_ESC_ESC:
                out.append(SLIP_ESC)
            else:
                # Séquence invalide : on garde db tel quel, l'octet suivant sera lu normalement.
                where = f"position {i}"
                issues.append(f"échappement SLIP invalide (db suivi de {nxt:02x}) {where}"
                              if nxt is not None else f"échappement SLIP tronqué en fin de frame ({where})")
                out.append(b)
                positions.append(i)
                i += 1
                continue
            positions.append(i)
            i += 2
            continue
        if b == SLIP_END:
            issues.append(f"délimiteur c0 au milieu de la frame (position {i})")
        else:
            out.append(b)
            positions.append(i)
        i += 1
    return Deframed(bytes(out), positions, issues)
