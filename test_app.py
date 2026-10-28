import os

# La clave de prueba debe existir ANTES de importar la app
os.environ.setdefault("ADMIN_API_KEY", "clave-de-prueba")

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
CLAVE = {"X-API-Key": os.environ["ADMIN_API_KEY"]}
NUEVO = {"name": "Registro de prueba", "category": "music"}


# ---------- Casos de éxito ----------
def test_listado_ok():
    """El listado responde 200 y trae la estructura de página."""
    r = client.get("/v1/records")
    assert r.status_code == 200
    assert set(r.json()) == {"items", "total", "limit", "offset"}


def test_detalle_ok():
    """Un ID que existe devuelve 200 y ese mismo registro."""
    primero = client.get("/v1/records").json()["items"][0]
    r = client.get(f"/v1/records/{primero['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == primero["id"]


def test_filtro_sin_resultados():
    """Un filtro válido sin coincidencias es 200 con lista vacía."""
    r = client.get("/v1/records?category=no-existe")
    assert r.status_code == 200
    assert r.json()["items"] == []


# ---------- Ausencia y entrada inválida ----------
def test_detalle_inexistente():
    """Un ID que no existe devuelve 404."""
    assert client.get("/v1/records/999999").status_code == 404


def test_limit_invalido():
    """limit=0 está fuera del rango permitido: 422."""
    assert client.get("/v1/records?limit=0").status_code == 422


def test_post_datos_invalidos():
    """Un nombre vacío se rechaza con 422 (aunque la clave sea válida)."""
    r = client.post("/v1/records", json={"name": "", "category": "x"}, headers=CLAVE)
    assert r.status_code == 422


# ---------- Seguridad ----------
def test_post_sin_clave():
    """Sin cabecera X-API-Key no se puede crear: 401."""
    assert client.post("/v1/records", json=NUEVO).status_code == 401


def test_post_clave_erronea():
    """Con una clave incorrecta tampoco: 401."""
    r = client.post("/v1/records", json=NUEVO, headers={"X-API-Key": "mala"})
    assert r.status_code == 401


def test_post_y_delete_con_clave_valida():
    """Con la clave correcta se crea (201) y se borra (204); borrar de nuevo da 404."""
    creado = client.post("/v1/records", json=NUEVO, headers=CLAVE)
    assert creado.status_code == 201
    id_nuevo = creado.json()["id"]

    assert client.delete(f"/v1/records/{id_nuevo}", headers=CLAVE).status_code == 204
    assert client.delete(f"/v1/records/{id_nuevo}", headers=CLAVE).status_code == 404