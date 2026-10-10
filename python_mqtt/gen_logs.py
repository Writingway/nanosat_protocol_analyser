#!/usr/bin/env python3
"""Génère des fichiers de logs NSP SYNTHÉTIQUES (in = demandes, out = réponses).

Format d'une ligne :  temps | date_emission | date_reception | data=c0...c0
Frame NSP (dans le SLIP) : DST | SRC | CTRL | DATA... | CRC (2 octets, little-endian)
CRC = CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), calculé de DST à la fin de DATA.

Usage : python3 gen_logs.py [nb_paires] [--broken]
"""
import random
import sys
from datetime import datetime, timedelta

SLIP_END, SLIP_ESC, SLIP_ESC_END, SLIP_ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD

# Adresses et CTRL inventés pour le banc (à adapter selon ton ICD)
ADDR_PC, ADDR_EQUIP = 0x11, 0x2A
CTRL_REQ = 0x84   # Poll=1, commande=4
CTRL_REP = 0x24   # ACK=1, commande=4


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def slip_encode(payload: bytes) -> bytes:
    out = bytearray([SLIP_END])
    for b in payload:
        if b == SLIP_END:
            out += bytes([SLIP_ESC, SLIP_ESC_END])
        elif b == SLIP_ESC:
            out += bytes([SLIP_ESC, SLIP_ESC_ESC])
        else:
            out.append(b)
    out.append(SLIP_END)
    return bytes(out)


def nsp_frame(dst: int, src: int, ctrl: int, data: bytes) -> bytes:
    body = bytes([dst, src, ctrl]) + data
    crc = crc16_ccitt_false(body)
    return slip_encode(body + crc.to_bytes(2, "little"))


def line(t0: datetime, t: datetime, frame: bytes) -> str:
    rx = t + timedelta(milliseconds=random.randint(1, 9))
    return (f"{(t - t0).total_seconds():.3f} | {t.isoformat(timespec='milliseconds')} | "
            f"{rx.isoformat(timespec='milliseconds')} | data={frame.hex()}")


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
    broken = "--broken" in sys.argv
    random.seed(42)
    t0 = t = datetime(2026, 10, 7, 9, 0, 0)
    lines_in, lines_out = [], []
    for _ in range(n):
        req = nsp_frame(ADDR_EQUIP, ADDR_PC, CTRL_REQ, bytes([0x0A, 0x90, 0x00, 0x30]))
        lines_in.append(line(t0, t, req))
        t += timedelta(milliseconds=random.randint(50, 200))
        data = b"".join(random.randint(0, 0xFFFF).to_bytes(2, "little") for _ in range(5))
        rep = nsp_frame(ADDR_PC, ADDR_EQUIP, CTRL_REP, data)
        lines_out.append(line(t0, t, rep))
        t += timedelta(seconds=1)

    if broken:  # frames invalides pour tester la robustesse
        bad = ["data=", "data=c0c0", "data=c0112a", "data=c0112a84ffff c0",
               "data=c0112a840a900030dead" + "c0", "pas une ligne de log",
               "data=" + "c0" + "00" * 5000 + "c0"]
        for b in bad:
            lines_out.append(f"0.000 | {t.isoformat()} | {t.isoformat()} | {b}" if b.startswith("data") else b)

    with open("archive_EquipSerialIn.txt", "w") as f:
        f.write("\n".join(lines_in) + "\n")
    with open("archive_EquipSerialOut.txt", "w") as f:
        f.write("\n".join(lines_out) + "\n")
    print(f"{len(lines_in)} demandes, {len(lines_out)} réponses écrites.")


if __name__ == "__main__":
    main()
