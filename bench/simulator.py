#!/usr/bin/env python3
"""Simulateur de banc(s) de test : trafic MQTT continu, réaliste, en boucle.

Chaque banc contient 3 équipements, chacun avec son protocole :
  gyro         NSP    (SLIP, CRC-16/CCITT-FALSE)   vitesses angulaires + température
  roue         ewc31  (fictif, CRC-16/XMODEM)      vitesse de roue qui suit une consigne
  capteur_sol  emea   (fictif, CRC-8)              photodiodes, éclairé / éclipse

Le « PC du banc » interroge chaque équipement (topic <banc>/<equip>/serial/in) et l'équipement
répond (topic <banc>/<equip>/serial/out), comme sur le vrai banc.
Variations de la vraie vie :
  - cadence irrégulière (gigue), latence de réponse variable avec pics occasionnels ;
  - télémesures qui évoluent lentement : orbite (soleil / éclipse), température, consignes de roue ;
  - anomalies rares : CRC faux, frame tronquée, pas de réponse, ligne de log corrompue.

Les encodeurs sont volontairement écrits ici, indépendamment du backend de l'analyseur :
un bug ne peut pas s'annuler des deux côtés.

Usage :
  python3 bench/simulator.py                    # 1 banc, temps réel, Ctrl+C pour arrêter
  python3 bench/simulator.py --benches 3        # 3 bancs en parallèle
  python3 bench/simulator.py --speed 5          # cadence x5
  python3 bench/simulator.py --errors 10        # 10x plus d'anomalies (test de robustesse)
  python3 bench/simulator.py --orbit 60         # orbite de 60 s pour voir vite les éclipses
"""
import argparse
import math
import random
import struct
import threading
import time
from datetime import datetime, timedelta

import paho.mqtt.client as mqtt

# --- Encodeurs (indépendants du backend) ---------------------------------------------


def crc16(data: bytes, init: int) -> int:
    """CRC-16 poly 0x1021 : init 0xFFFF = CCITT-FALSE (NSP), init 0 = XMODEM (ewc31)."""
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def slip(payload: bytes) -> bytes:
    body = payload.replace(b"\xdb", b"\xdb\xdd").replace(b"\xc0", b"\xdb\xdc")
    return b"\xc0" + body + b"\xc0"


def nsp(dst: int, src: int, ctrl: int, data: bytes) -> bytes:
    body = bytes([dst, src, ctrl]) + data
    return slip(body + crc16(body, 0xFFFF).to_bytes(2, "little"))


def ewc31(dst: int, src: int, cmd: int, data: bytes) -> bytes:
    body = struct.pack(">HHHHB", 0xEB90, dst, src, len(data), cmd) + data
    return body + crc16(body, 0).to_bytes(2, "big")


def emea(ident: int, seq: int, typ: int, data: bytes) -> bytes:
    body = bytes([ident, seq & 0xFF, typ, len(data)]) + data
    return body + bytes([crc8(body)])


# --- Monde simulé ----------------------------------------------------------------------


class Orbit:
    """Phase d'orbite partagée par un banc : soleil, éclipse, température."""

    def __init__(self, period: float, offset: float):
        self.period, self.t0 = period, time.monotonic() - offset

    def phase(self) -> float:  # 0..1
        return ((time.monotonic() - self.t0) / self.period) % 1.0

    def in_eclipse(self) -> bool:
        return 0.62 < self.phase() < 0.97  # ~35 % de l'orbite à l'ombre

    def temperature(self) -> float:
        """°C : chauffe au soleil, refroidit en éclipse, avec du bruit de mesure."""
        return 18 + 12 * math.sin(2 * math.pi * (self.phase() - 0.15)) + random.gauss(0, 0.3)


class Equipment(threading.Thread):
    name_in_topic = ""
    period = 1.0  # secondes entre deux requêtes
    latency_ms = 8.0  # latence de réponse typique

    def __init__(self, bench: "Bench", index: int):
        super().__init__(daemon=True)
        self.bench, self.index = bench, index
        self.topic = f"{bench.name}/{self.name_in_topic}/serial"

    # requête du PC, puis réponse de l'équipement (None = pas de réponse)
    def request(self) -> bytes: ...
    def response(self) -> bytes | None: ...

    def run(self):
        b = self.bench
        time.sleep(random.uniform(0, self.period))  # les équipements ne démarrent pas en phase
        while not b.stop.is_set():
            # Gigue de cadence ±15 %
            time.sleep(self.period / b.speed * random.uniform(0.85, 1.15))
            b.publish(f"{self.topic}/in", self.request())

            if b.anomaly(0.01):  # l'équipement ne répond pas (timeout côté banc)
                b.stats["sans réponse"] += 1
                continue
            latency = random.lognormvariate(math.log(self.latency_ms), 0.35)
            if b.chance(0.02):
                latency *= 12  # pic de latence (bus chargé)
            time.sleep(latency / 1000 / b.speed)
            frame = self.response()
            if frame is not None:
                b.publish(f"{self.topic}/out", b.damage(frame))


class Gyro(Equipment):
    """NSP : le PC (0x11) lit les vitesses angulaires du gyro (0x2A)."""

    name_in_topic, period, latency_ms = "gyro", 0.5, 6.0
    PC, GYRO = 0x11, 0x2A

    def __init__(self, bench, index):
        super().__init__(bench, index)
        self.counter = random.randint(0, 5000)
        self.rate = [random.gauss(0, 20) for _ in range(3)]  # mdeg/s

    def request(self):
        return nsp(self.GYRO, self.PC, 0x84, bytes([0x0A, 0x90, 0x00, 0x30]))

    def response(self):
        self.counter = (self.counter + 1) & 0xFFFF
        # Marche aléatoire lente = dérive de l'attitude, + bruit de mesure
        self.rate = [r * 0.98 + random.gauss(0, 3) for r in self.rate]
        temp = int(self.bench.orbit.temperature() * 100)
        data = struct.pack("<hhhhH", *(int(r) for r in self.rate), temp, self.counter)
        return nsp(self.PC, self.GYRO, 0x24, data)


class Wheel(Equipment):
    """ewc31 : l'OBC lit la vitesse de la roue ; de temps en temps il envoie une nouvelle consigne."""

    name_in_topic, period, latency_ms = "roue", 1.0, 12.0
    OBC = 0x0001

    def __init__(self, bench, index):
        super().__init__(bench, index)
        self.addr = 0x0101 + index % 3  # roue X, Y ou Z selon le banc
        self.speed_rpm = random.uniform(-500, 500)
        self.setpoint = self.speed_rpm
        self.pending_cmd = 0x10

    def request(self):
        if self.bench.chance(0.08):  # nouvelle consigne de vitesse
            self.setpoint = random.choice([-3000, -1500, 0, 1500, 3000]) + random.uniform(-200, 200)
            self.pending_cmd = 0x11
            return ewc31(self.addr, self.OBC, 0x11, struct.pack(">i", int(self.setpoint)))
        self.pending_cmd = 0x10
        return ewc31(self.addr, self.OBC, 0x10, b"")

    def response(self):
        if self.pending_cmd == 0x11:
            return ewc31(self.OBC, self.addr, 0x91, b"\x00")  # acquittement
        # La roue rejoint sa consigne progressivement (inertie), courant proportionnel à l'effort
        error = self.setpoint - self.speed_rpm
        self.speed_rpm += error * 0.15 + random.gauss(0, 2)
        current_ma = int(min(1500, abs(error) * 0.8 + 60 + random.gauss(0, 5)))
        temp = int(self.bench.orbit.temperature() * 10 + 50)
        return ewc31(self.OBC, self.addr, 0x90, struct.pack(">ihh", int(self.speed_rpm), current_ma, temp))


class SunSensor(Equipment):
    """emea : l'OBC demande la télémesure ; 4 photodiodes, à zéro en éclipse."""

    name_in_topic, period, latency_ms = "capteur_sol", 2.0, 4.0
    OBC, SENSOR = 0x01, 0x41

    def __init__(self, bench, index):
        super().__init__(bench, index)
        self.seq = random.randint(0, 255)

    def request(self):
        self.seq = (self.seq + 1) & 0xFF
        return emea(self.OBC, self.seq, 0x01, b"")

    def response(self):
        o = self.bench.orbit
        if o.in_eclipse():
            diodes = [max(0, int(random.gauss(15, 4))) for _ in range(4)]  # bruit d'obscurité
        else:
            angle = 2 * math.pi * o.phase()
            diodes = [max(0, int(3000 * max(0.0, math.cos(angle - k * math.pi / 2)) + random.gauss(40, 15)))
                      for k in range(4)]
        if self.bench.anomaly(0.005):
            return emea(self.SENSOR, self.seq, 0xEE, b"\x02")  # code erreur capteur
        return emea(self.SENSOR, self.seq, 0x81, struct.pack(">4H", *(min(d, 0xFFFF) for d in diodes)))


# --- Banc --------------------------------------------------------------------------------


class Bench:
    def __init__(self, name: str, client: mqtt.Client, args, index: int):
        self.name, self.client, self.speed, self.errors = name, client, args.speed, args.errors
        self.orbit = Orbit(args.orbit, offset=index * args.orbit / 3)  # bancs décalés sur l'orbite
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.stats = {"publiés": 0, "CRC faux": 0, "tronquées": 0, "sans réponse": 0, "lignes corrompues": 0}
        self.t0 = datetime.now()
        self.equipments = [cls(self, index) for cls in (Gyro, Wheel, SunSensor)]

    def chance(self, p: float) -> bool:
        return random.random() < p

    def anomaly(self, p: float) -> bool:
        """Comme chance(), mais modulé par --errors (0 = jamais d'anomalie)."""
        return random.random() < p * self.errors

    def damage(self, frame: bytes) -> bytes | str:
        """Anomalies rares, comme sur un vrai bus série."""
        if self.anomaly(0.005):
            self.stats["CRC faux"] += 1
            i = random.randrange(1, len(frame) - 1)
            return frame[:i] + bytes([frame[i] ^ (1 << random.randrange(8))]) + frame[i + 1:]  # 1 bit inversé
        if self.anomaly(0.003):
            self.stats["tronquées"] += 1
            return frame[: random.randrange(1, len(frame))]
        if self.anomaly(0.001):
            self.stats["lignes corrompues"] += 1
            return "#### UART overrun ####"
        return frame

    def publish(self, topic: str, frame: bytes | str) -> None:
        tx = datetime.now()
        rx = tx + timedelta(milliseconds=random.uniform(0.5, 4))
        if isinstance(frame, str):
            line = frame
        else:
            line = (f"{(tx - self.t0).total_seconds():.3f} | {tx.isoformat(timespec='milliseconds')} | "
                    f"{rx.isoformat(timespec='milliseconds')} | data={frame.hex()}")
        self.client.publish(topic, line, qos=0)
        with self.lock:
            self.stats["publiés"] += 1

    def start(self):
        for eq in self.equipments:
            eq.start()


def make_client(client_id: str) -> mqtt.Client:
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:  # paho-mqtt 1.x (paquet apt)
        return mqtt.Client(client_id=client_id)


def main():
    ap = argparse.ArgumentParser(description="Simulateur de bancs de test MQTT (boucle infinie).")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--benches", type=int, default=1, help="nombre de bancs (banc1, banc2, …)")
    ap.add_argument("--speed", type=float, default=1.0, help="multiplicateur de cadence")
    ap.add_argument("--errors", type=float, default=1.0, help="multiplicateur du taux d'anomalies (0 = aucune)")
    ap.add_argument("--orbit", type=float, default=300.0, help="durée d'une orbite simulée en secondes")
    ap.add_argument("--duration", type=float, default=0, help="arrêt après N secondes (0 = infini)")
    ap.add_argument("--seed", type=int, help="graine aléatoire (rejouer la même séquence)")
    a = ap.parse_args()
    if a.seed is not None:
        random.seed(a.seed)

    client = make_client(f"simulateur-{random.randrange(1 << 16):04x}")
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    client.connect(a.host, a.port)
    client.loop_start()  # reconnexion automatique si le broker redémarre

    benches = [Bench(f"banc{i + 1}", client, a, i) for i in range(a.benches)]
    for b in benches:
        b.start()
    print(f"{len(benches)} banc(s) × 3 équipements → mqtt://{a.host}:{a.port}  "
          f"(topics bancN/<equipement>/serial/in|out). Ctrl+C pour arrêter.")

    start = time.monotonic()
    try:
        while not a.duration or time.monotonic() - start < a.duration:
            time.sleep(5)
            for b in benches:
                s = b.stats
                ombre = "éclipse" if b.orbit.in_eclipse() else "soleil"
                print(f"[{datetime.now():%H:%M:%S}] {b.name} ({ombre}, orbite {b.orbit.phase():.0%}) "
                      + ", ".join(f"{k} {v}" for k, v in s.items()))
    except KeyboardInterrupt:
        pass
    for b in benches:
        b.stop.set()
    time.sleep(0.3)
    client.loop_stop()
    client.disconnect()
    print("Simulateur arrêté.")


if __name__ == "__main__":
    main()
