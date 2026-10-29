"""Configuración común de los tests. Se ejecuta ANTES de importar la aplicación."""
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Los tests trabajan con una COPIA de los datos y sus propias claves: nunca tocan data/products.json
_TMP = Path(tempfile.mkdtemp())
shutil.copy(Path(__file__).parent / "data" / "products.json", _TMP / "products.json")
os.environ.update(
    ADMIN_API_KEY="clave-admin-de-prueba",
    INGEST_API_KEY="clave-ingesta-de-prueba",
    DATA_FILE=str(_TMP / "products.json"),
    INGEST_COOLDOWN_SECONDS="0",
    SEARCH_RATE_LIMIT_PER_MINUTE="1000",
    WIKI_USER_AGENT="TrendWatchTests/1.0 (tests@example.com)",
)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import search  # noqa: E402


@pytest.fixture(scope="session")
def client():
    return TestClient(main.app)


@pytest.fixture()
def admin():
    return {"X-API-Key": os.environ["ADMIN_API_KEY"]}


@pytest.fixture()
def ingester():
    return {"X-API-Key": os.environ["INGEST_API_KEY"]}


@pytest.fixture(autouse=True)
def clean_state():
    """Cada test parte sin caché, sin límites acumulados y con la espera entre ingestas desactivada."""
    search._cache.clear()
    main._search_hits.clear()
    main._last_ingest.clear()
    main.INGEST_COOLDOWN = 0
    yield


class FakeResponse:
    """Respuesta falsa de requests para simular la API externa."""

    def __init__(self, status=200, data=None, bad_json=False):
        self.status_code, self._data, self._bad_json = status, data, bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("no es JSON")
        return self._data
