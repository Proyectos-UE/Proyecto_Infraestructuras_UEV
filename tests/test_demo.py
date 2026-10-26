"""Prueba del servicio externo simulado y del esquema estricto."""
import datetime as dt

from fastapi.testclient import TestClient
from trendwatch.demo_source import app as demo_app
from trendwatch.connectors import demo as demo_module
from trendwatch.connectors.demo import DemoConnector
from trendwatch.services import InvalidSourceData, SourceUnavailable
import pytest


def test_demo_registros_validos():
    with TestClient(demo_app) as cliente:
        respuesta = cliente.get("/datos", params={"term": "mini proyectores"})
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert len(datos) == 35
    assert all(0 <= r["interes"] <= 100 for r in datos)


def test_demo_errores():
    with TestClient(demo_app) as cliente:
        assert cliente.get("/datos", params={"term": "mini proyectores", "escenario": "no_disponible"}).status_code == 503
        assert cliente.get("/datos", params={"term": "mini proyectores", "escenario": "invalidos"}).json()[0]["interes"] == 150


def test_conector_rechaza_respuesta_invalida(monkeypatch):
    class Respuesta:
        status_code = 200
        def json(self):
            return [{"fecha": "nada", "interes": 150}]
    monkeypatch.setattr(demo_module.requests, "get", lambda *args, **kw: Respuesta())
    with pytest.raises(InvalidSourceData):
        DemoConnector().fetch("proyectores", dt.date(2026, 1, 1), dt.date(2026, 2, 1))


def test_conector_maneja_http_503(monkeypatch):
    class Respuesta:
        status_code = 503
    monkeypatch.setattr(demo_module.requests, "get", lambda *args, **kw: Respuesta())
    with pytest.raises(SourceUnavailable):
        DemoConnector().fetch("proyectores", dt.date(2026, 1, 1), dt.date(2026, 2, 1))
