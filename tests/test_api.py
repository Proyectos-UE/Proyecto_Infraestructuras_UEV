"""Endpoints: casos correctos, inválidos y de acceso no autorizado."""
import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from trendwatch import config
from trendwatch.api import main as api_module
from trendwatch.api.main import app, get_session
from trendwatch.connectors.base import Point
from trendwatch.db import init_db
from trendwatch.models import Keyword, Observation
from trendwatch.services import InvalidSourceData, SourceUnavailable, save_points

TEST_KEY = "clave-administrador-pruebas-123456789"
AUTH = {"X-API-Key": TEST_KEY}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", TEST_KEY)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        c.Session = Session
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_health_y_documentacion(client):
    assert client.get("/health").json() == {"status": "ok"}
    doc = client.get("/openapi.json").json()
    assert "/ingest" in doc["paths"]
    assert "APIKeyHeader" in doc["components"]["securitySchemes"]


def test_lectura_publica_y_escritura_protegida(client):
    assert client.get("/watchlist").status_code == 200
    assert client.post("/watchlist", json={"term": "Air fryer"}).status_code == 401
    assert client.post("/watchlist", json={"term": "Air fryer"}, headers={"X-API-Key": "mal"}).status_code == 401
    assert client.post("/ingest").status_code == 401
    assert client.delete("/watchlist/Air fryer").status_code == 401


def test_clave_no_configurada_falla_de_forma_segura(client, monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "")
    assert client.post("/watchlist", json={"term": "Air fryer"}, headers=AUTH).status_code == 503


def test_watchlist_crud(client):
    assert client.post("/watchlist", json={"term": "Air fryer"}, headers=AUTH).status_code == 201
    assert client.post("/watchlist", json={"term": "Air fryer"}, headers=AUTH).status_code == 409
    assert client.get("/watchlist").json() == ["Air fryer"]
    assert client.delete("/watchlist/Air fryer", headers=AUTH).status_code == 204
    assert client.get("/watchlist").json() == []


@pytest.mark.parametrize("body", [
    {"term": ""}, {"term": " "}, {"term": "a"}, {"term": "a" * 101}, {},
    {"term": 123}, {"term": "valido", "campo_extra": "no"},
])
def test_entradas_invalidas(client, body):
    assert client.post("/watchlist", json=body, headers=AUTH).status_code == 422


def test_parametros_y_termino_inexistente(client):
    assert client.get("/trends/nada").status_code == 404
    assert client.get("/rankings/rising?limit=0").status_code == 422
    assert client.get("/trends/nada?days=1000").status_code == 422
    assert client.get("/trends/nada?source=desconocida").status_code == 422


def test_spike_end_to_end(client):
    client.post("/watchlist", json={"term": "Producto viral"}, headers=AUTH)
    start = dt.date(2026, 1, 1)
    pts = [Point(start + dt.timedelta(days=i), 100 + (i % 5)) for i in range(40)]
    pts.append(Point(start + dt.timedelta(days=40), 600))
    with client.Session() as s:
        kw = s.scalar(select(Keyword))
        save_points(s, kw, "wikipedia", pts)
    resp = client.get("/trends/Producto viral/spike")
    assert resp.status_code == 200 and resp.json()["is_spike"] is True
    assert client.get("/rankings/rising").json()[0]["term"] == "Producto viral"
    assert len(client.get("/trends/Producto viral?days=10").json()["points"]) == 10


def test_ingesta_realiza_consulta_y_no_duplica(client, monkeypatch):
    hoy = dt.date.today()

    class FuenteFalsa:
        name = "demo"

        def fetch(self, term, start, end):
            return [Point(hoy - dt.timedelta(days=i), float(30 + i)) for i in range(2)]

    monkeypatch.setattr(api_module, "build_connectors", lambda: [FuenteFalsa()])
    client.post("/watchlist", json={"term": "proyectores"}, headers=AUTH)
    primero = client.post("/ingest", headers=AUTH)
    assert primero.status_code == 200
    assert primero.json()["resultados"][0]["registros"]["demo"] == 2
    segundo = client.post("/ingest", headers=AUTH)
    assert segundo.status_code == 200
    with client.Session() as s:
        assert s.scalar(select(func.count()).select_from(Observation)) == 2


def test_ingesta_rechaza_datos_invalidos_sin_guardar(client, monkeypatch):
    class FuenteInvalida:
        name = "demo"
        def fetch(self, term, start, end):
            return [Point(dt.date.today(), 150.0)]

    monkeypatch.setattr(api_module, "build_connectors", lambda: [FuenteInvalida()])
    client.post("/watchlist", json={"term": "proyectores"}, headers=AUTH)
    resp = client.post("/ingest", headers=AUTH)
    assert resp.status_code == 502
    with client.Session() as s:
        assert s.scalar(select(func.count()).select_from(Observation)) == 0


def test_ingesta_fuente_caida(client, monkeypatch):
    class FuenteCaida:
        name = "demo"
        def fetch(self, term, start, end):
            raise SourceUnavailable("API caída")

    monkeypatch.setattr(api_module, "build_connectors", lambda: [FuenteCaida()])
    client.post("/watchlist", json={"term": "proyectores"}, headers=AUTH)
    assert client.post("/ingest", headers=AUTH).status_code == 503


def test_ingesta_fuente_con_fecha_duplicada(client, monkeypatch):
    class FuenteInvalida:
        name = "demo"
        def fetch(self, term, start, end):
            return [Point(dt.date.today(), 22.0), Point(dt.date.today(), 22.0)]

    monkeypatch.setattr(api_module, "build_connectors", lambda: [FuenteInvalida()])
    client.post("/watchlist", json={"term": "proyectores"}, headers=AUTH)
    assert client.post("/ingest", headers=AUTH).status_code == 502
