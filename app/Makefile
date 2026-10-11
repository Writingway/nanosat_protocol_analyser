PY := backend/.venv/bin/python
MANAGE := cd backend && .venv/bin/python manage.py

.PHONY: help install db migrate back ingest front dev test lint import-demo replay bench

help:
	@echo "make install      venv Python + dépendances"
	@echo "make db           démarre PostgreSQL (Docker)"
	@echo "make migrate      applique les migrations"
	@echo "make back         API Django (uvicorn, port 8000, rechargement auto)"
	@echo "make ingest       service de capture live MQTT (config/ingest.yaml)"
	@echo "make front        IHM React en dev (http://localhost:5173)"
	@echo "make dev          back + ingest + front ensemble (Ctrl+C arrête tout)"
	@echo "make replay       rejoue les logs du banc NSP sur MQTT (SPEED=1, 0 = rafale)"
	@echo "make bench        simulateur de bancs en boucle, 3 protocoles (BENCHES=1 ERRORS=1)"
	@echo "make test         tests backend"
	@echo "make lint         ruff"
	@echo "make import-demo  génère et importe les logs du banc NSP"

install:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt
	test -f .env || cp .env.example .env
	cd frontend && npm install

db:
	docker compose up -d db

migrate:
	$(MANAGE) migrate

back:
	cd backend && .venv/bin/uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --reload

ingest:
	$(MANAGE) mqtt_ingest

front:
	cd frontend && npm run dev

# Trois process en parallèle ; Ctrl+C les arrête tous.
dev:
	@trap 'kill 0' INT TERM; \
	$(MAKE) back & $(MAKE) ingest & $(MAKE) front & wait

SPEED ?= 1
replay:
	cd ../python_mqtt && python3 replay.py --in archive_EquipSerialIn.txt --out archive_EquipSerialOut.txt --speed $(SPEED)

test:
	cd backend && .venv/bin/python -m pytest -q
	cd frontend && npm run typecheck

lint:
	cd backend && .venv/bin/ruff check .

import-demo:
	cd ../python_mqtt && python3 gen_logs.py 500 --broken
	$(MANAGE) import_log ../../python_mqtt/archive_EquipSerialIn.txt ../../python_mqtt/archive_EquipSerialOut.txt \
		--equipment equip --protocol nsp --bench banc-local --force

# Simulateur de bancs en boucle (Ctrl+C pour arrêter). Ex. : make bench BENCHES=3 ERRORS=5
BENCHES ?= 1
ERRORS ?= 1
bench:
	python3 bench/simulator.py --benches $(BENCHES) --errors $(ERRORS)
