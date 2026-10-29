"""Tests de la API: casos correctos, entradas inválidas, ausencia de recursos y acceso no autorizado."""
import datetime as dt
import json
import os
from pathlib import Path

import main
from spike import analyze

NUEVO = {"name": "Producto de prueba", "category": "hogar"}
ESTABLE = [100, 102, 98, 101, 99] * 8  # 40 días sin cambios bruscos


def serie(valores, fin=dt.date(2026, 6, 30)):
    n = len(valores)
    return [{"date": (fin - dt.timedelta(days=n - 1 - i)).isoformat(), "value": v} for i, v in enumerate(valores)]


# ---------- Casos correctos ----------
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_listado_ok(client):
    r = client.get("/v1/products")
    assert r.status_code == 200
    assert set(r.json()) == {"items", "total", "limit", "offset"}


def test_detalle_ok(client):
    primero = client.get("/v1/products").json()["items"][0]
    r = client.get(f"/v1/products/{primero['id']}")
    assert r.status_code == 200 and r.json()["id"] == primero["id"]


def test_filtro_y_paginacion(client):
    r = client.get("/v1/products?category=movilidad").json()
    assert r["total"] >= 1 and all(p["category"] == "movilidad" for p in r["items"])
    assert len(client.get("/v1/products?limit=3&offset=1").json()["items"]) == 3
    assert client.get("/v1/products?category=no-existe").json()["items"] == []


def test_serie_ok(client):
    r = client.get("/v1/products/1/series?days=10")
    assert r.status_code == 200 and len(r.json()["series"]) == 10


# ---------- Entradas inválidas y recursos ausentes ----------
def test_detalle_inexistente(client):
    r = client.get("/v1/products/999999")
    assert r.status_code == 404 and r.json() == {"detail": "Product not found"}


def test_limit_invalido(client):
    assert client.get("/v1/products?limit=0").status_code == 422


def test_post_datos_invalidos(client, admin):
    assert client.post("/v1/products", json={"name": "", "category": "x"}, headers=admin).status_code == 422


def test_post_campo_desconocido(client, admin):
    assert client.post("/v1/products", json={**NUEVO, "admin": True}, headers=admin).status_code == 422


def test_post_fechas_repetidas(client, admin):
    repetida = serie([1, 2])
    repetida[1]["date"] = repetida[0]["date"]
    assert client.post("/v1/products", json={**NUEVO, "series": repetida}, headers=admin).status_code == 422


def test_post_valor_negativo(client, admin):
    assert client.post("/v1/products", json={**NUEVO, "series": serie([-5])}, headers=admin).status_code == 422


# ---------- Acceso no autorizado (401) y sin permiso (403) ----------
def test_post_sin_clave_401(client):
    assert client.post("/v1/products", json=NUEVO).status_code == 401


def test_post_clave_erronea_401(client):
    r = client.post("/v1/products", json=NUEVO, headers={"X-API-Key": "mala"})
    assert r.status_code == 401 and r.headers["WWW-Authenticate"] == "APIKey"


def test_endpoints_protegidos_sin_clave(client):
    assert client.delete("/v1/products/1").status_code == 401
    assert client.get("/v1/admin/summary").status_code == 401
    assert client.get("/v1/admin/ingestions").status_code == 401


def test_clave_de_ingesta_no_puede_crear_ni_borrar_403(client, ingester):
    """Autorización: la clave de ingesta es válida (no es 401) pero no tiene permisos de administrador."""
    assert client.post("/v1/products", json=NUEVO, headers=ingester).status_code == 403
    assert client.delete("/v1/products/1", headers=ingester).status_code == 403
    assert client.get("/v1/admin/summary", headers=ingester).status_code == 403


# ---------- Escritura con clave de administrador ----------
def test_post_y_delete_con_clave_valida(client, admin):
    creado = client.post("/v1/products", json=NUEVO, headers=admin)
    assert creado.status_code == 201
    nuevo_id = creado.json()["id"]
    assert creado.headers["Location"] == f"/v1/products/{nuevo_id}"
    assert client.delete(f"/v1/products/{nuevo_id}", headers=admin).status_code == 204
    assert client.delete(f"/v1/products/{nuevo_id}", headers=admin).status_code == 404


def test_nombre_duplicado_409(client, admin):
    creado = client.post("/v1/products", json={**NUEVO, "name": "Duplicado"}, headers=admin)
    assert client.post("/v1/products", json={**NUEVO, "name": "duplicado"}, headers=admin).status_code == 409
    client.delete(f"/v1/products/{creado.json()['id']}", headers=admin)


def test_id_borrado_no_se_reutiliza(client, admin):
    a = client.post("/v1/products", json={**NUEVO, "name": "Efímero A"}, headers=admin).json()["id"]
    client.delete(f"/v1/products/{a}", headers=admin)
    b = client.post("/v1/products", json={**NUEVO, "name": "Efímero B"}, headers=admin).json()["id"]
    assert b != a
    client.delete(f"/v1/products/{b}", headers=admin)


def test_los_cambios_se_guardan_en_disco(client, admin):
    creado = client.post("/v1/products", json={**NUEVO, "name": "Persistente"}, headers=admin).json()
    en_disco = json.loads(Path(os.environ["DATA_FILE"]).read_text(encoding="utf-8"))
    assert "Persistente" in [p["name"] for p in en_disco]
    client.delete(f"/v1/products/{creado['id']}", headers=admin)
    en_disco = json.loads(Path(os.environ["DATA_FILE"]).read_text(encoding="utf-8"))
    assert "Persistente" not in [p["name"] for p in en_disco]


def test_resumen_admin(client, admin):
    r = client.get("/v1/admin/summary", headers=admin)
    assert r.status_code == 200 and r.json()["products_loaded"] >= 1


# ---------- Detección de picos ----------
def test_pico_detectado_y_ranking(client, admin):
    p = client.post("/v1/products", json={"name": "Viral", "category": "test", "series": serie(ESTABLE + [400])}, headers=admin).json()
    spike = client.get(f"/v1/products/{p['id']}/spike").json()
    assert spike["is_spike"] is True and spike["z_score"] > 3
    assert client.get("/v1/rankings/rising?limit=1").json()[0]["id"] == p["id"]
    client.delete(f"/v1/products/{p['id']}", headers=admin)


def test_serie_estable_no_es_pico(client, admin):
    p = client.post("/v1/products", json={"name": "Estable", "category": "test", "series": serie(ESTABLE + [101])}, headers=admin).json()
    assert client.get(f"/v1/products/{p['id']}/spike").json()["is_spike"] is False
    client.delete(f"/v1/products/{p['id']}", headers=admin)


def test_spike_sin_historico_409(client, admin):
    p = client.post("/v1/products", json={**NUEVO, "name": "Sin datos"}, headers=admin).json()
    assert client.get(f"/v1/products/{p['id']}/spike").status_code == 409
    client.delete(f"/v1/products/{p['id']}", headers=admin)


def test_detector_directo():
    assert analyze([1, 2, 3]) is None
    assert analyze(ESTABLE + [400])["is_spike"] is True


# ---------- Documentación OpenAPI ----------
def test_openapi_documenta_seguridad_e_ingesta(client):
    spec = client.get("/openapi.json").json()
    assert "ApiKeyAuth" in spec["components"]["securitySchemes"]
    assert "/v1/ingest" in spec["paths"] and "/v1/products/{product_id}/ingest" in spec["paths"]
    post_ingest = spec["paths"]["/v1/ingest"]["post"]
    assert {"401", "403", "422", "502"} <= set(post_ingest["responses"])
    assert client.get("/docs").status_code == 200


def test_error_inesperado_no_filtra_la_traza():
    from fastapi.testclient import TestClient

    @main.app.get("/_boom", include_in_schema=False)
    def boom():
        raise RuntimeError("secreto interno")

    r = TestClient(main.app, raise_server_exceptions=False).get("/_boom")
    assert r.status_code == 500 and r.json() == {"detail": "Internal server error"}
