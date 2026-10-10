"""Configuration Django de l'analyseur.

Toutes les valeurs réglables viennent de variables d'environnement
(fichier `.env` à la racine du projet, voir `.env.example`).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
PROJECT_DIR = BASE_DIR.parent  # racine du dépôt


def _load_dotenv(path: Path) -> None:
    """Lecteur .env minimal : KEY=VALUE, lignes # ignorées. N'écrase pas l'environnement."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(PROJECT_DIR / ".env")


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def env_path(key: str, default: str) -> Path:
    """Chemin relatif → relatif au dossier backend/."""
    p = Path(env(key, default))
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = env("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if h.strip()]
ALLOWED_NETS = [n.strip() for n in env("ALLOWED_NETS", "").split(",") if n.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "rest_framework",
    "protocols",
    "captures",
]

MIDDLEWARE = [
    "config.middleware.AllowedNetworksMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = None

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "analyseur"),
        "USER": env("DB_USER", "analyseur"),
        "PASSWORD": env("DB_PASSWORD", "analyseur"),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Tout est stocké en UTC ; l'IHM affiche en heure locale du navigateur.
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "fr-fr"
USE_I18N = False

# Fuseau des dates sans fuseau écrites dans les logs du banc.
LOG_TIMEZONE = env("LOG_TIMEZONE", "Europe/Paris")

# Dossier des fichiers YAML de protocoles (rechargés à chaud).
PROTOCOLS_DIR = env_path("PROTOCOLS_DIR", "../protocols")
# Configuration de la capture live MQTT.
INGEST_CONFIG = env_path("INGEST_CONFIG", "../config/ingest.yaml")

# Fichiers du front React buildé (servis par WhiteNoise en production).
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.exists() else []

# Taille max d'un fichier de log importé.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # ?format= est utilisé par nos exports (csv / log), pas par la négociation de DRF.
    "URL_FORMAT_OVERRIDE": None,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
