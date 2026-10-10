# Analyseur de protocoles d'équipements satellite

Application web interne, **passive**, qui décode l'en-tête des frames échangées avec les
équipements (NSP et protocoles maison) à partir de **fichiers de logs** ou d'un flux **MQTT live**.
Les protocoles sont décrits en **YAML** et rechargés à chaud. Brief : [STAGE_ANALYSEUR_PROTOCOLES.md](STAGE_ANALYSEUR_PROTOCOLES.md).

```
[Fichier log] ─┐
               ├─> Lecteur ─> Moteur YAML ─> PostgreSQL ─> API Django ─> IHM React
[Broker MQTT] ─┘
```

## Démarrage rapide (dev)

Prérequis : Python 3.12, Docker, Mosquitto (live), Node 22 (IHM).

```bash
make install      # venv + dépendances, crée .env
make db           # PostgreSQL 16 dans Docker (127.0.0.1:5432)
make migrate
make import-demo  # génère des logs NSP (avec frames cassées) et les importe
make back         # API sur http://127.0.0.1:8000/api/
make test
```

## Arborescence

| Dossier | Rôle |
|---|---|
| `protocols/` | fichiers YAML des protocoles (`nsp`, `ewc31` et `emea` fictifs) |
| `backend/protocols/engine/` | moteur de décodage, sans Django : schéma YAML, CRC, SLIP, décodeur |
| `backend/protocols/registry.py` | chargement + rechargement à chaud des YAML |
| `backend/captures/` | modèles, lecture des logs, ingestion par lots, API |
| `python_mqtt/` | banc NSP d'origine (génération / rejeu / observation) |
| `docs/` | décisions d'architecture, guide YAML |

## API

| Méthode | URL | Rôle |
|---|---|---|
| GET | `/api/protocols/` | protocoles chargés, version, erreurs YAML |
| GET/PUT | `/api/protocols/<nom>/` | lire / enregistrer un YAML (refusé s'il est invalide) |
| POST | `/api/protocols/validate/` | valider un YAML, décoder un hexa d'essai |
| GET/POST | `/api/captures/` | liste / import (`file_in`, `file_out`, `equipment`, `protocol`, `bench`) |
| GET/DELETE | `/api/captures/<id>/` | résumé (sources, protocoles, statuts) / suppression |
| GET | `/api/captures/<id>/export/?format=csv\|log` | export (mêmes filtres que la liste) |
| GET | `/api/frames/?capture=&direction=&status=&f.DST=0x2A&from=&to=&offset=&limit=` | liste filtrée |
| GET | `/api/frames/<id>/` | arbre des champs, octets, CRC lu / calculé |
| GET | `/api/sources/` | sources connues |

## Import en ligne de commande

```bash
cd backend
.venv/bin/python manage.py import_log ../python_mqtt/archive_EquipSerial*.txt --equipment equip --protocol nsp
```
