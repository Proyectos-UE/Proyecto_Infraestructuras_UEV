"""Tests de la búsqueda libre (fuentes simuladas, sin Internet)."""
import datetime as dt

import main
import search


def semanas(valores, inicio=dt.date(2026, 1, 4)):
    return [(inicio + dt.timedelta(weeks=i), v) for i, v in enumerate(valores)]


def bloqueado(*a, **k):
    raise search.SourceUnavailable("429")


def test_to_monthly_suma_y_media():
    puntos = [(dt.date(2026, 1, 1), 10), (dt.date(2026, 1, 15), 30), (dt.date(2026, 2, 1), 5)]
    hoy = dt.date(2026, 2, 20)
    assert search.to_monthly(puntos, "sum", 12, hoy) == [
        {"month": "2026-01", "value": 40.0, "partial": False},
        {"month": "2026-02", "value": 5.0, "partial": True},
    ]
    assert search.to_monthly(puntos, "mean", 12, hoy)[0]["value"] == 20.0
    assert len(search.to_monthly(puntos, "sum", 1, hoy)) == 1


def test_busqueda_con_google_trends(client, monkeypatch):
    monkeypatch.setattr(search, "google_trends_series", lambda *a, **k: semanas([20, 40, 60, 80, 100]))
    datos = client.get("/v1/search?q=calcetines de navidad").json()
    assert datos["source"] == "trends" and "no" in datos["unit"].lower()
    assert datos["months"][0]["month"] == "2026-01" and datos["months"][0]["value"] == 50.0


def test_busqueda_cae_a_wikipedia_si_google_falla(client, monkeypatch):
    monkeypatch.setattr(search, "google_trends_series", bloqueado)
    monkeypatch.setattr(search, "wikipedia_daily", lambda *a, **k: [(dt.date.today().replace(day=1), 7.0)])
    datos = client.get("/v1/search?q=Pádel").json()
    assert datos["source"] == "wikipedia" and "Se usó Wikipedia" in datos["note"]


def test_busqueda_google_bloqueado_y_sin_wikipedia_503(client, monkeypatch):
    monkeypatch.setattr(search, "google_trends_series", bloqueado)
    monkeypatch.setattr(search, "wikipedia_daily", lambda *a, **k: [])
    assert client.get("/v1/search?q=algo raro").status_code == 503


def test_busqueda_sin_datos_404(client, monkeypatch):
    monkeypatch.setattr(search, "google_trends_series", lambda *a, **k: [])
    monkeypatch.setattr(search, "wikipedia_daily", lambda *a, **k: [])
    assert client.get("/v1/search?q=xyzxyzxyz").status_code == 404


def test_busqueda_parametros_invalidos(client):
    for url in ("/v1/search?q=a", "/v1/search?q=padel&months=0", "/v1/search?q=padel&source=otra",
                "/v1/search?q=padel&geo=ESP", "/v1/search"):
        assert client.get(url).status_code == 422, url


def test_busqueda_usa_cache(client, monkeypatch):
    llamadas = []
    monkeypatch.setattr(search, "google_trends_series", lambda *a, **k: llamadas.append(1) or semanas([10, 20]))
    client.get("/v1/search?q=navidad")
    client.get("/v1/search?q=Navidad")
    assert len(llamadas) == 1


def test_busqueda_limite_de_peticiones_429(client, monkeypatch):
    monkeypatch.setattr(main, "SEARCH_RATE_LIMIT", 2)
    monkeypatch.setattr(search, "google_trends_series", lambda *a, **k: semanas([10, 20]))
    assert client.get("/v1/search?q=uno").status_code == 200
    assert client.get("/v1/search?q=dos").status_code == 200
    r = client.get("/v1/search?q=tres")
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
