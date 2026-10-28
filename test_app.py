import datetime as dt
import os

# La clave de prueba debe existir ANTES de importar la app
os.environ.setdefault("ADMIN_API_KEY", "clave-de-prueba")

from fastapi.testclient import TestClient

import fetch_data
from main import app
from spike import analyze

client = TestClient(app)
CLAVE = {"X-API-Key": os.environ["ADMIN_API_KEY"]}
NUEVO = {"name": "Producto de prueba", "category": "hogar"}


def serie(valores, fin=dt.date(2026, 6, 30)):
    """Construye una serie diaria que termina en `fin`."""
    n = len(valores)
    return [
        {"date": (fin - dt.timedelta(days=n - 1 - i)).isoformat(), "value": v}
        for i, v in enumerate(valores)
    ]


ESTABLE = [100, 102, 98, 101, 99] * 8  # 40 días sin cambios bruscos


# ---------- Casos de éxito ----------
def test_listado_ok():
    """El listado responde 200 y trae la estructura de página."""
    r = client.get("/v1/products")
    assert r.status_code == 200
    assert set(r.json()) == {"items", "total", "limit", "offset"}


def test_detalle_ok():
    """Un ID que existe devuelve 200 y ese mismo producto."""
    primero = client.get("/v1/products").json()["items"][0]
    r = client.get(f"/v1/products/{primero['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == primero["id"]


def test_filtro_sin_resultados():
    """Un filtro válido sin coincidencias es 200 con lista vacía."""
    r = client.get("/v1/products?category=no-existe")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_paginacion():
    r = client.get("/v1/products?limit=3&offset=1").json()
    assert len(r["items"]) == 3 and r["offset"] == 1


def test_serie_ok():
    primero = client.get("/v1/products").json()["items"][0]
    r = client.get(f"/v1/products/{primero['id']}/series?days=10")
    assert r.status_code == 200
    assert len(r.json()["series"]) == 10


# ---------- Ausencia y entrada inválida ----------
def test_detalle_inexistente():
    """Un ID que no existe devuelve 404."""
    assert client.get("/v1/products/999999").status_code == 404


def test_limit_invalido():
    """limit=0 está fuera del rango permitido: 422."""
    assert client.get("/v1/products?limit=0").status_code == 422


def test_post_datos_invalidos():
    """Un nombre vacío se rechaza con 422 (aunque la clave sea válida)."""
    r = client.post("/v1/products", json={"name": "", "category": "x"}, headers=CLAVE)
    assert r.status_code == 422


def test_post_campo_desconocido():
    r = client.post("/v1/products", json={**NUEVO, "admin": True}, headers=CLAVE)
    assert r.status_code == 422


def test_post_fechas_repetidas():
    """Una serie con la misma fecha dos veces se rechaza con 422."""
    repetida = serie([1, 2])
    repetida[1]["date"] = repetida[0]["date"]
    r = client.post("/v1/products", json={**NUEVO, "series": repetida}, headers=CLAVE)
    assert r.status_code == 422


# ---------- Seguridad ----------
def test_post_sin_clave():
    """Sin cabecera X-API-Key no se puede crear: 401."""
    assert client.post("/v1/products", json=NUEVO).status_code == 401


def test_post_clave_erronea():
    """Con una clave incorrecta tampoco: 401."""
    r = client.post("/v1/products", json=NUEVO, headers={"X-API-Key": "mala"})
    assert r.status_code == 401


def test_delete_y_resumen_exigen_clave():
    assert client.delete("/v1/products/1").status_code == 401
    assert client.get("/v1/admin/summary").status_code == 401


def test_post_y_delete_con_clave_valida():
    """Con la clave correcta se crea (201) y se borra (204); borrar de nuevo da 404."""
    creado = client.post("/v1/products", json=NUEVO, headers=CLAVE)
    assert creado.status_code == 201
    id_nuevo = creado.json()["id"]
    assert creado.headers["Location"] == f"/v1/products/{id_nuevo}"

    assert client.delete(f"/v1/products/{id_nuevo}", headers=CLAVE).status_code == 204
    assert client.delete(f"/v1/products/{id_nuevo}", headers=CLAVE).status_code == 404


def test_nombre_duplicado():
    creado = client.post("/v1/products", json={**NUEVO, "name": "Duplicado"}, headers=CLAVE)
    r = client.post("/v1/products", json={**NUEVO, "name": "duplicado"}, headers=CLAVE)
    assert r.status_code == 409
    client.delete(f"/v1/products/{creado.json()['id']}", headers=CLAVE)


def test_id_borrado_no_se_reutiliza():
    a = client.post("/v1/products", json={**NUEVO, "name": "Efímero A"}, headers=CLAVE).json()["id"]
    client.delete(f"/v1/products/{a}", headers=CLAVE)
    b = client.post("/v1/products", json={**NUEVO, "name": "Efímero B"}, headers=CLAVE).json()["id"]
    assert b != a
    client.delete(f"/v1/products/{b}", headers=CLAVE)


# ---------- Detección de picos ----------
def test_pico_detectado():
    """Un producto que de golpe cuadruplica su interés se marca como pico."""
    p = client.post(
        "/v1/products", json={"name": "Viral", "category": "test", "series": serie(ESTABLE + [400])},
        headers=CLAVE,
    ).json()
    spike = client.get(f"/v1/products/{p['id']}/spike").json()
    assert spike["is_spike"] is True and spike["z_score"] > 3

    ranking = client.get("/v1/rankings/rising?limit=1").json()
    assert ranking[0]["id"] == p["id"]
    client.delete(f"/v1/products/{p['id']}", headers=CLAVE)


def test_serie_estable_no_es_pico():
    p = client.post(
        "/v1/products", json={"name": "Estable", "category": "test", "series": serie(ESTABLE + [101])},
        headers=CLAVE,
    ).json()
    assert client.get(f"/v1/products/{p['id']}/spike").json()["is_spike"] is False
    client.delete(f"/v1/products/{p['id']}", headers=CLAVE)


def test_spike_sin_historico_suficiente():
    """Un producto sin serie no se puede analizar: 409."""
    p = client.post("/v1/products", json={**NUEVO, "name": "Sin datos"}, headers=CLAVE).json()
    assert client.get(f"/v1/products/{p['id']}/spike").status_code == 409
    client.delete(f"/v1/products/{p['id']}", headers=CLAVE)


def test_detector_directo():
    assert analyze([1, 2, 3]) is None
    assert analyze(ESTABLE + [400])["is_spike"] is True


def test_resumen_con_clave():
    r = client.get("/v1/admin/summary", headers=CLAVE)
    assert r.status_code == 200
    assert r.json()["products_loaded"] >= 1


# ---------- Descarga de datos reales (sin Internet: se simula la respuesta) ----------
class FalsaRespuesta:
    def __init__(self, status, datos=None):
        self.status_code, self._datos = status, datos or {}

    def json(self):
        return self._datos


def test_fetch_data_parsea_wikipedia(monkeypatch):
    items = {"items": [{"timestamp": "2026010100", "views": 10}, {"timestamp": "2026010200", "views": 25}]}
    monkeypatch.setattr(fetch_data.requests, "get", lambda *a, **k: FalsaRespuesta(200, items))
    out = fetch_data.fetch_series("Freidora de aire", dt.date(2026, 1, 1), dt.date(2026, 1, 2), "test")
    assert out == [{"date": "2026-01-01", "value": 10.0}, {"date": "2026-01-02", "value": 25.0}]


def test_fetch_data_404_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(fetch_data.requests, "get", lambda *a, **k: FalsaRespuesta(404))
    assert fetch_data.fetch_series("Nada", dt.date(2026, 1, 1), dt.date(2026, 1, 2), "test") == []
