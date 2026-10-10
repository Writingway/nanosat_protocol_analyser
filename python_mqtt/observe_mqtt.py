#!/usr/bin/env python3
"""Affiche en hexa les frames reçues sur MQTT (in / out). Ne décode rien.

Usage : python3 observe_mqtt.py [--host localhost] [--topic 'equip/serial/#']
"""
import argparse
from datetime import datetime

import paho.mqtt.client as mqtt


def extract_hex(payload: bytes) -> str:
    """Le message a le format d'une ligne de log : on récupère ce qui suit 'data='."""
    text = payload.decode(errors="replace")
    if "data=" in text:
        return text.split("data=", 1)[1].strip()
    return payload.hex()  # message brut binaire


def on_connect(client, userdata, *args):
    client.subscribe(userdata["topic"])
    print(f"Abonné à {userdata['topic']}")


def on_message(client, userdata, msg):
    h = extract_hex(msg.payload)
    spaced = " ".join(h[i:i + 2] for i in range(0, len(h), 2))
    sens = "IN " if msg.topic.endswith("/in") else "OUT" if msg.topic.endswith("/out") else "???"
    print(f"{datetime.now():%H:%M:%S.%f} {sens} qos={msg.qos} {spaced}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--topic", default="equip/serial/#")
    a = ap.parse_args()

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata={"topic": a.topic})
    except AttributeError:
        client = mqtt.Client(userdata={"topic": a.topic})
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(a.host, a.port)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
