"""Algorithmes de CRC disponibles dans les fichiers YAML (clé `crc.type`).

Chaque algorithme est décrit par ses paramètres standards (catalogue RevEng).
Pour en ajouter un : une ligne dans CRC_ALGORITHMS, rien d'autre.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CrcAlgorithm:
    width: int  # nombre de bits (8 ou 16)
    poly: int
    init: int
    reflected: bool = False  # True = bits traités poids faible d'abord (ex. Modbus)
    xorout: int = 0
    table: tuple[int, ...] = field(default=(), repr=False, compare=False)

    @property
    def size(self) -> int:
        """Taille en octets."""
        return self.width // 8


def _reflect(value: int, width: int) -> int:
    return int(f"{value:0{width}b}"[::-1], 2)


def _build_table(width: int, poly: int, reflected: bool) -> tuple[int, ...]:
    """Table de 256 valeurs pré-calculées : un accès par octet au lieu de 8 décalages."""
    mask = (1 << width) - 1
    table = []
    if reflected:
        rpoly = _reflect(poly, width)
        for byte in range(256):
            crc = byte
            for _ in range(8):
                crc = (crc >> 1) ^ rpoly if crc & 1 else crc >> 1
            table.append(crc)
    else:
        top = 1 << (width - 1)
        for byte in range(256):
            crc = byte << (width - 8)
            for _ in range(8):
                crc = ((crc << 1) ^ poly) if crc & top else (crc << 1)
            table.append(crc & mask)
    return tuple(table)


def _algo(width: int, poly: int, init: int, reflected: bool = False, xorout: int = 0) -> CrcAlgorithm:
    return CrcAlgorithm(width, poly, init, reflected, xorout, _build_table(width, poly, reflected))


CRC_ALGORITHMS: dict[str, CrcAlgorithm] = {
    "crc16_ccitt_false": _algo(16, 0x1021, 0xFFFF),  # NSP
    "crc16_xmodem": _algo(16, 0x1021, 0x0000),
    "crc16_modbus": _algo(16, 0x8005, 0xFFFF, reflected=True),
    "crc8": _algo(8, 0x07, 0x00),
}


def compute_crc(name: str, data: bytes) -> int:
    algo = CRC_ALGORITHMS[name]
    crc = algo.init
    table = algo.table
    if algo.reflected:
        for b in data:
            crc = (crc >> 8) ^ table[(crc ^ b) & 0xFF]
    else:
        shift = algo.width - 8
        mask = (1 << algo.width) - 1
        for b in data:
            crc = ((crc << 8) & mask) ^ table[((crc >> shift) ^ b) & 0xFF]
    return crc ^ algo.xorout
