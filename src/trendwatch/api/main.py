"""API REST de TrendWatch: `uvicorn trendwatch.api.main:app`."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, init_db
from ..detection.spike import detect_spike
from ..models import Keyword
from ..services import get_series


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TrendWatch API", version="0.1.0", lifespan=lifespan)


def get_session():
    with SessionLocal() as session:
        yield session


class KeywordIn(BaseModel):
    term: str


def _get_keyword(session: Session, term: str) -> Keyword:
    kw = session.scalar(select(Keyword).where(Keyword.term == term))
    if kw is None:
        raise HTTPException(404, f"'{term}' no está en la watchlist")
    return kw


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/watchlist")
def list_watchlist(session: Session = Depends(get_session)):
    return [k.term for k in session.scalars(select(Keyword).order_by(Keyword.term))]


@app.post("/watchlist", status_code=201)
def add_keyword(body: KeywordIn, session: Session = Depends(get_session)):
    term = body.term.strip()
    if not term:
        raise HTTPException(422, "El término no puede estar vacío")
    if session.scalar(select(Keyword).where(Keyword.term == term)):
        raise HTTPException(409, "Ya existe en la watchlist")
    session.add(Keyword(term=term))
    session.commit()
    return {"term": term}


@app.delete("/watchlist/{term}", status_code=204)
def remove_keyword(term: str, session: Session = Depends(get_session)):
    session.delete(_get_keyword(session, term))
    session.commit()


@app.get("/trends/{term}")
def get_trend(
    term: str,
    source: str = "wikipedia",
    days: int = Query(90, ge=1, le=730),
    session: Session = Depends(get_session),
):
    series = get_series(session, _get_keyword(session, term), source, days)
    return {
        "term": term,
        "source": source,
        "points": [{"date": d.date().isoformat(), "value": v} for d, v in series.items()],
    }


@app.get("/trends/{term}/spike")
def get_spike(
    term: str,
    source: str = "wikipedia",
    window: int = Query(28, ge=7, le=180),
    z_threshold: float = Query(3.0, gt=0),
    session: Session = Depends(get_session),
):
    series = get_series(session, _get_keyword(session, term), source)
    result = detect_spike(series, window=window, z_threshold=z_threshold)
    if result is None:
        raise HTTPException(409, "Histórico insuficiente: espera a que el worker recoja más días")
    return {"term": term, "source": source, **result.__dict__}


@app.get("/rankings/rising")
def rising(source: str = "wikipedia", limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    ranking = []
    for kw in session.scalars(select(Keyword)):
        res = detect_spike(get_series(session, kw, source))
        if res:
            ranking.append({"term": kw.term, "growth": res.growth, "z_score": res.z_score, "is_spike": res.is_spike})
    return sorted(ranking, key=lambda r: r["growth"], reverse=True)[:limit]
