PY := backend/.venv/bin/python
MANAGE := cd backend && .venv/bin/python manage.py

.PHONY: help install db migrate back test lint import-demo

help:
	@echo "make install      venv Python + dépendances"
	@echo "make db           démarre PostgreSQL (Docker)"
	@echo "make migrate      applique les migrations"
	@echo "make back         API Django (uvicorn, port 8000, rechargement auto)"
	@echo "make test         tests backend"
	@echo "make lint         ruff"
	@echo "make import-demo  génère et importe les logs du banc NSP"

install:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt
	test -f .env || cp .env.example .env

db:
	docker compose up -d db

migrate:
	$(MANAGE) migrate

back:
	cd backend && .venv/bin/uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --reload

test:
	cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/bin/ruff check .

import-demo:
	cd python_mqtt && python3 gen_logs.py 500 --broken
	$(MANAGE) import_log ../python_mqtt/archive_EquipSerialIn.txt ../python_mqtt/archive_EquipSerialOut.txt \
		--equipment equip --protocol nsp --bench banc-local --force
