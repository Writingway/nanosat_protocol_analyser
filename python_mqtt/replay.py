#!/usr/bin/env python3
"""Rejoue des fichiers de logs sur MQTT, en respectant (ou en accélérant) le temps.

Chaque ligne du log est publiée TELLE QUELLE (même format que le fichier).
  fichier in  -> topic <prefix>/serial/in
  fichier out -> topic <prefix>/serial/out

Usage :
  python3 replay.py --in archive_EquipSerialIn.txt --out archive_EquipSerialOut.txt
  python3 replay.py ... --speed 10      # 10x plus vite
  python3 replay.py ... --speed 0       # le plus vite possible
"""
import argparse
import time
from datetime import datetime

import paho.mqtt.client as mqtt


def make_client() -> mqtt.Client:
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:  # paho-mqtt 1.x (paquet apt Ubuntu)
        return mqtt.Client()


def read_log(path: str, topic: str):
    """Renvoie [(datetime, topic, ligne)]. Les lignes sans date valide gardent la précédente."""
    events, last = [], datetime.min
    with open(path) as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if not raw:
                continue
            parts = [p.strip() for p in raw.split("|")]
            try:
                last = datetime.fromisoformat(parts[1])
            except (IndexError, ValueError):
                pass
            events.append((last, topic, raw))
    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="file_in")
    ap.add_argument("--out", dest="file_out")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--prefix", default="equip")
    ap.add_argument("--qos", type=int, default=0)
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()

    events = []
    if a.file_in:
        events += read_log(a.file_in, f"{a.prefix}/serial/in")
    if a.file_out:
        events += read_log(a.file_out, f"{a.prefix}/serial/out")
    events.sort(key=lambda e: e[0])  # ordre chronologique, in et out mélangés
    if not events:
        ap.error("donne au moins --in ou --out")

    client = make_client()
    client.connect(a.host, a.port)
    client.loop_start()

    start_wall, start_log = time.monotonic(), events[0][0]
    for i, (t, topic, payload) in enumerate(events, 1):
        if a.speed > 0:
            target = (t - start_log).total_seconds() / a.speed
            delay = target - (time.monotonic() - start_wall)
            if delay > 0:
                time.sleep(delay)
        client.publish(topic, payload, qos=a.qos)
        print(f"[{i}/{len(events)}] {topic}  {payload[:80]}")

    time.sleep(0.5)  # laisse partir les derniers messages
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
