import datetime as dt

from trendwatch.connectors import wikipedia
from trendwatch.connectors.google_trends_csv import read_trends_csv
from trendwatch.connectors.wikipedia import WikipediaConnector


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload or {}

    def json(self):
        return self._payload


def test_wikipedia_parsea_respuesta(monkeypatch):
    payload = {"items": [
        {"timestamp": "2026010100", "views": 10},
        {"timestamp": "2026010200", "views": 25},
    ]}
    captured = {}

    def fake_get(url, headers, timeout):
        captured["url"], captured["headers"] = url, headers
        return FakeResp(200, payload)

    monkeypatch.setattr(wikipedia.requests, "get", fake_get)
    pts = WikipediaConnector(user_agent="test-agent").fetch("Air Fryer", dt.date(2026, 1, 1), dt.date(2026, 1, 2))
    assert [p.value for p in pts] == [10.0, 25.0]
    assert pts[0].date == dt.date(2026, 1, 1)
    assert "Air_Fryer" in captured["url"] and captured["headers"]["User-Agent"] == "test-agent"


def test_wikipedia_404_devuelve_lista_vacia(monkeypatch):
    monkeypatch.setattr(wikipedia.requests, "get", lambda *a, **k: FakeResp(404))
    assert WikipediaConnector().fetch("Nada", dt.date(2026, 1, 1), dt.date(2026, 1, 2)) == []


def test_csv_google_trends(tmp_path):
    f = tmp_path / "trends.csv"
    f.write_text(
        "Categoría: Todas las categorías\n\nDía,air fryer: (España)\n2026-01-01,50\n2026-01-02,<1\n2026-01-03,100\n",
        encoding="utf-8",
    )
    pts = read_trends_csv(f)
    assert [p.value for p in pts] == [50.0, 1.0, 100.0]
