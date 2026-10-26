import datetime as dt

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from trendwatch.api.main import app, get_session
from trendwatch.connectors.base import Point
from trendwatch.db import init_db
from trendwatch.models import Keyword
from trendwatch.services import save_points


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    c = TestClient(app)
    c.Session = Session
    yield c
    app.dependency_overrides.clear()


def test_watchlist_crud(client):
    assert client.post("/watchlist", json={"term": "Air fryer"}).status_code == 201
    assert client.post("/watchlist", json={"term": "Air fryer"}).status_code == 409
    assert client.get("/watchlist").json() == ["Air fryer"]
    assert client.delete("/watchlist/Air fryer").status_code == 204
    assert client.get("/watchlist").json() == []


def test_termino_inexistente_da_404(client):
    assert client.get("/trends/nada").status_code == 404


def test_spike_end_to_end(client):
    client.post("/watchlist", json={"term": "Producto viral"})
    start = dt.date(2026, 1, 1)
    pts = [Point(start + dt.timedelta(days=i), 100 + (i % 5)) for i in range(40)]
    pts.append(Point(start + dt.timedelta(days=40), 600))
    with client.Session() as s:
        kw = s.scalar(select(Keyword))
        save_points(s, kw, "wikipedia", pts)
    r = client.get("/trends/Producto viral/spike")
    assert r.status_code == 200 and r.json()["is_spike"] is True
    assert client.get("/rankings/rising").json()[0]["term"] == "Producto viral"
    assert len(client.get("/trends/Producto viral?days=10").json()["points"]) == 10
