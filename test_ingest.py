"""Tests del proceso de ingesta: validación, reglas, errores de la API externa y permisos."""
import datetime as dt

import pytest

import ingest
import main
from conftest import FakeResponse

HOY = dt.date(2026, 10, 28)
START, END = ingest.window(10, HOY)  # 2026-10-18 .. 2026-10-27


def item(day, views=10, **extra):
    return {"timestamp": f"{day:%Y%m%d}00", "views": views, **extra}


# ---------- Tubería: validación y reglas ----------
def test_ventana_termina_ayer():
    assert ingest.window(7, HOY) == (dt.date(2026, 10, 21), dt.date(2026, 10, 27))


def test_registros_validos_se_aceptan():
    raw = {"items": [item(START), item(START + dt.timedelta(days=1), 25, project="es.wikipedia")]}
    r = ingest.validate(raw, START, END)
    assert r.received == 2 and r.rejected == 0 and r.points[START] == 10.0


def test_cada_registro_invalido_se_rechaza_por_separado():
    raw = {"items": [
        item(START),                                    # válido
        {"timestamp": "2026101800", "views": -3},        # visitas negativas
        {"timestamp": "no-es-fecha", "views": 5},        # formato de fecha inválido
        {"timestamp": "2026023000", "views": 5},         # 30 de febrero: fecha imposible
        item(dt.date(2020, 1, 1)),                       # fuera de la ventana
        item(START),                                     # fecha repetida
        "basura",                                        # ni siquiera es un registro
        {"timestamp": "2026101900", "views": "muchas"},  # tipo incorrecto
    ]}
    r = ingest.validate(raw, START, END)
    assert r.received == 8 and len(r.points) == 1 and r.rejected == 7
    assert len(r.samples) == ingest.MAX_SAMPLES


def test_regla_de_calidad_rechaza_la_tanda_entera():
    malos = [{"timestamp": "x", "views": 1}] * 3
    buenos = [item(START + dt.timedelta(days=i)) for i in range(7)]
    with pytest.raises(ingest.QualityError):
        ingest.check_quality(ingest.validate({"items": buenos + malos}, START, END))  # 30 % inválidos
    ingest.check_quality(ingest.validate({"items": buenos + malos[:1]}, START, END))  # 12 %: pasa


def test_api_simulada_es_determinista_y_valida():
    a = ingest.simulate_wikimedia("Pádel", START, END)
    assert a == ingest.simulate_wikimedia("Pádel", START, END)
    r = ingest.validate(a, START, END)
    assert r.rejected == 0 and len(r.points) == 10


# ---------- Endpoint con la API simulada ----------
def test_ingesta_simulada_correcta_e_idempotente(client, admin):
    p = client.post("/v1/products", json={"name": "Ingesta A", "category": "test"}, headers=admin).json()
    url = f"/v1/products/{p['id']}/ingest?source=simulated&days=30"
    r1 = client.post(url, headers=admin)
    assert r1.status_code == 200
    rep = r1.json()
    assert rep["status"] == "ok" and rep["received"] == rep["accepted"] == rep["inserted"] == 30
    assert rep["rejected"] == 0 and rep["total_points"] == 30 and rep["replaced_previous_source"] is False
    # Repetir la ingesta no duplica nada
    rep2 = client.post(url, headers=admin).json()
    assert rep2["inserted"] == 0 and rep2["updated"] == 0 and rep2["total_points"] == 30
    assert client.get(f"/v1/products/{p['id']}").json()["source"] == "simulated"
    client.delete(f"/v1/products/{p['id']}", headers=admin)


def test_cambiar_de_fuente_sustituye_la_serie(client, admin):
    """El producto 1 viene con datos 'demo': una serie nunca mezcla fuentes."""
    assert client.get("/v1/products/1").json()["source"] == "demo"
    rep = client.post("/v1/products/1/ingest?source=simulated&days=14", headers=admin).json()
    assert rep["replaced_previous_source"] is True and rep["total_points"] == 14


def test_la_ingesta_permite_detectar_el_pico_simulado(client, admin):
    p = client.post("/v1/products", json={"name": "Freidora de aire", "category": "x"}, headers=admin)
    if p.status_code == 409:  # ya existe en los datos de ejemplo
        pid = next(i["id"] for i in client.get("/v1/products?limit=100").json()["items"] if i["name"] == "Freidora de aire")
    else:
        pid = p.json()["id"]
    client.post(f"/v1/products/{pid}/ingest?source=simulated&days=60", headers=admin)
    assert client.get(f"/v1/products/{pid}/spike").json()["is_spike"] is True


# ---------- Permisos y parámetros ----------
def test_ingesta_sin_clave_401(client):
    assert client.post("/v1/products/1/ingest?source=simulated").status_code == 401
    assert client.post("/v1/ingest?source=simulated").status_code == 401


def test_ingesta_clave_erronea_401(client):
    assert client.post("/v1/ingest?source=simulated", headers={"X-API-Key": "mala"}).status_code == 401


def test_clave_de_ingesta_puede_ingerir(client, ingester):
    assert client.post("/v1/products/2/ingest?source=simulated&days=10", headers=ingester).status_code == 200


def test_parametros_invalidos_422(client, admin):
    assert client.post("/v1/products/1/ingest?source=simulated&days=3", headers=admin).status_code == 422
    assert client.post("/v1/products/1/ingest?source=simulated&days=999", headers=admin).status_code == 422
    assert client.post("/v1/products/1/ingest?source=otra", headers=admin).status_code == 422


def test_ingesta_de_producto_inexistente_404(client, admin):
    assert client.post("/v1/products/999999/ingest?source=simulated", headers=admin).status_code == 404


# ---------- Fallos de la API externa real (simulados con requests falso) ----------
def test_wikipedia_correcta(client, admin, monkeypatch):
    items = {"items": [item(START + dt.timedelta(days=i), 100 + i) for i in range(10)]}
    monkeypatch.setattr(ingest, "window", lambda days, today=None: (START, END))
    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse(200, items))
    rep = client.post("/v1/products/3/ingest?source=wikipedia&days=10", headers=admin).json()
    assert rep["status"] == "ok" and rep["accepted"] == 10


def test_wikipedia_sin_conexion_502(client, admin, monkeypatch):
    def caido(*a, **k):
        raise ingest.requests.ConnectionError("sin red")

    monkeypatch.setattr(ingest.requests, "get", caido)
    r = client.post("/v1/products/3/ingest?source=wikipedia", headers=admin)
    assert r.status_code == 502 and "External API error" in r.json()["detail"]


def test_wikipedia_error_5xx_y_429_dan_502(client, admin, monkeypatch):
    for codigo in (503, 429):
        monkeypatch.setattr(ingest.requests, "get", lambda *a, c=codigo, **k: FakeResponse(c))
        assert client.post("/v1/products/3/ingest?source=wikipedia", headers=admin).status_code == 502


def test_wikipedia_respuesta_ilegible_502(client, admin, monkeypatch):
    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse(200, bad_json=True))
    assert client.post("/v1/products/3/ingest?source=wikipedia", headers=admin).status_code == 502
    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse(200, {"otra": "cosa"}))
    assert client.post("/v1/products/3/ingest?source=wikipedia", headers=admin).status_code == 502


def test_wikipedia_articulo_inexistente_no_toca_los_datos(client, admin, monkeypatch):
    antes = client.get("/v1/products/4").json()["points"]
    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse(404))
    rep = client.post("/v1/products/4/ingest?source=wikipedia", headers=admin).json()
    assert rep["status"] == "no_data" and rep["accepted"] == 0
    assert client.get("/v1/products/4").json()["points"] == antes


def test_datos_de_mala_calidad_422_y_no_se_carga_nada(client, admin, monkeypatch):
    antes = client.get("/v1/products/5").json()
    mala = {"items": [item(START)] + [{"timestamp": "mal", "views": 1}] * 4}  # 80 % inválidos
    monkeypatch.setattr(ingest, "window", lambda days, today=None: (START, END))
    monkeypatch.setattr(ingest.requests, "get", lambda *a, **k: FakeResponse(200, mala))
    r = client.post("/v1/products/5/ingest?source=wikipedia&days=10", headers=admin)
    assert r.status_code == 422 and "nothing was loaded" in r.json()["detail"]
    assert client.get("/v1/products/5").json() == antes


def test_sin_user_agent_503(client, admin, monkeypatch):
    monkeypatch.delenv("WIKI_USER_AGENT")
    assert client.post("/v1/products/3/ingest?source=wikipedia", headers=admin).status_code == 503


def test_espera_minima_entre_ingestas_429(client, admin, monkeypatch):
    monkeypatch.setattr(main, "INGEST_COOLDOWN", 60)
    assert client.post("/v1/products/6/ingest?source=simulated&days=7", headers=admin).status_code == 200
    r = client.post("/v1/products/6/ingest?source=simulated&days=7", headers=admin)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


# ---------- Ingesta por lotes y registro ----------
def test_lote_informa_de_los_fallos_sin_parar(client, admin, monkeypatch):
    original = ingest.fetch_raw

    def a_veces_falla(source, title, *a, **k):
        if title == "Pádel":
            raise ingest.UpstreamError("simulado")
        return original(source, title, *a, **k)

    monkeypatch.setattr(ingest, "fetch_raw", a_veces_falla)
    r = client.post("/v1/ingest?source=simulated&days=7&category=deporte", headers=admin).json()
    assert r["requested"] == r["succeeded"] + r["failed"] and r["failed"] == 1
    assert r["errors"][0]["name"] == "Pádel" and r["errors"][0]["status_code"] == 502


def test_registro_de_ingestas_solo_para_admin(client, admin, ingester):
    client.post("/v1/products/7/ingest?source=simulated&days=7", headers=admin)
    assert client.get("/v1/admin/ingestions", headers=ingester).status_code == 403
    runs = client.get("/v1/admin/ingestions?limit=1", headers=admin).json()
    assert runs[0]["product_id"] == 7 and runs[0]["status"] == "ok"
