"""API REST de TrendWatch con OpenAPI y escritura protegida por clave API."""
from __future__ import annotations
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..db import SessionLocal, init_db
from ..detection.spike import detect_spike
from ..models import Keyword
from ..services import InvalidSourceData, SourceUnavailable, get_series, ingest_keyword
from ..worker import build_connectors


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="TrendWatch API",
    description="Consulta de tendencias y detección de picos. Las escrituras requieren una clave de administrador.",
    version="0.2.0",
    lifespan=lifespan,
)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_admin(api_key: str | None = Security(api_key_header)):
    if len(config.API_KEY) < 16:
        raise HTTPException(503, "El administrador debe configurar API_KEY (mínimo 16 caracteres)")
    if api_key is None or not secrets.compare_digest(api_key, config.API_KEY):
        raise HTTPException(401, "Clave API ausente o incorrecta")


def get_session():
    with SessionLocal() as session:
        yield session


class KeywordIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    term: str = Field(min_length=2, max_length=100)


Source = Literal["wikipedia", "demo", "pytrends", "google_trends_csv"]


def _get_keyword(session: Session, term: str) -> Keyword:
    kw = session.scalar(select(Keyword).where(Keyword.term == term))
    if kw is None:
        raise HTTPException(404, f"'{term}' no está en la watchlist")
    return kw


@app.get("/health", tags=["General"])
def health():
    return {"status": "ok"}


@app.get("/watchlist", tags=["Watchlist"])
def list_watchlist(session: Session = Depends(get_session)):
    return [k.term for k in session.scalars(select(Keyword).order_by(Keyword.term))]


@app.post("/watchlist", status_code=201, tags=["Watchlist"], dependencies=[Depends(require_admin)])
def add_keyword(body: KeywordIn, session: Session = Depends(get_session)):
    if session.scalar(select(Keyword).where(Keyword.term == body.term)):
        raise HTTPException(409, "Ya existe en la watchlist")
    session.add(Keyword(term=body.term))
    session.commit()
    return {"term": body.term}


@app.delete("/watchlist/{term}", status_code=204, tags=["Watchlist"], dependencies=[Depends(require_admin)])
def remove_keyword(term: str, session: Session = Depends(get_session)):
    session.delete(_get_keyword(session, term))
    session.commit()


@app.post("/ingest", tags=["Ingesta"], dependencies=[Depends(require_admin)])
def ingest_now(session: Session = Depends(get_session)):
    """Recoge ahora la información desde la API externa seleccionada en SOURCE_MODE."""
    keywords = list(session.scalars(select(Keyword).order_by(Keyword.term)))
    try:
        conectores = build_connectors()
        resultados = []
        for keyword in keywords:
            escritos = ingest_keyword(session, keyword, conectores, config.HISTORY_DAYS)
            resultados.append({"term": keyword.term, "registros": escritos})
    except InvalidSourceData:
        raise HTTPException(502, "La fuente externa devolvió registros inválidos")
    except SourceUnavailable:
        raise HTTPException(503, "La fuente externa no está disponible")
    except ValueError:
        raise HTTPException(503, "La fuente externa no está configurada correctamente")
    return {"procesados": len(resultados), "resultados": resultados}


@app.get("/trends/{term}", tags=["Tendencias"])
def get_trend(
    term: str,
    source: Source = "wikipedia",
    days: int = Query(90, ge=1, le=730),
    session: Session = Depends(get_session),
):
    series = get_series(session, _get_keyword(session, term), source, days)
    return {"term": term, "source": source, "points": [
        {"date": d.date().isoformat(), "value": v} for d, v in series.items()
    ]}


@app.get("/trends/{term}/spike", tags=["Tendencias"])
def get_spike(
    term: str,
    source: Source = "wikipedia",
    window: int = Query(28, ge=7, le=180),
    z_threshold: float = Query(3.0, gt=0, le=100),
    session: Session = Depends(get_session),
):
    series = get_series(session, _get_keyword(session, term), source)
    result = detect_spike(series, window=window, z_threshold=z_threshold)
    if result is None:
        raise HTTPException(409, "Histórico insuficiente: hay que ingerir más datos")
    return {"term": term, "source": source, **result.__dict__}


@app.get("/rankings/rising", tags=["Tendencias"])
def rising(
    source: Source = "wikipedia",
    limit: int = Query(10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    ranking = []
    for kw in session.scalars(select(Keyword)):
        res = detect_spike(get_series(session, kw, source))
        if res:
            ranking.append({"term": kw.term, "growth": res.growth, "z_score": res.z_score, "is_spike": res.is_spike})
    return sorted(ranking, key=lambda r: r["growth"], reverse=True)[:limit]
