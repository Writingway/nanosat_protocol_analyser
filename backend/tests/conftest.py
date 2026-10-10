import pytest

from protocols.registry import get_registry


@pytest.fixture(autouse=True)
def _fresh_version_cache():
    """Chaque test repart d'une base vide : le cache sha256 → id de version doit l'être aussi."""
    get_registry()._version_ids.clear()
    yield
    get_registry()._version_ids.clear()
