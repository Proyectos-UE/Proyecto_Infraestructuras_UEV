"""Lógica de ingesta y consulta (compartida por la API y el worker)."""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .connectors.base import Connector
from .models import Keyword, Observation

log = logging.getLogger(__name__)


def save_points(session: Session, keyword: Keyword, source: str, points) -> int:
    """Inserta o actualiza observaciones. Devuelve cuántas se escribieron."""
    existing = {
        o.date: o
        for o in session.scalars(
            select(Observation).where(Observation.keyword_id == keyword.id, Observation.source == source)
        )
    }
    written = 0
    for p in points:
        obs = existing.get(p.date)
        if obs is None:
            session.add(Observation(keyword_id=keyword.id, source=source, date=p.date, value=p.value))
        else:
            obs.value = p.value
        written += 1
    session.commit()
    return written


def ingest_keyword(session: Session, keyword: Keyword, connectors: list[Connector], days: int) -> dict[str, int]:
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    result = {}
    for conn in connectors:
        points = conn.fetch(keyword.term, start, end)
        result[conn.name] = save_points(session, keyword, conn.name, points)
        log.info("%s/%s: %s puntos", keyword.term, conn.name, result[conn.name])
    return result


def get_series(session: Session, keyword: Keyword, source: str, days: int | None = None) -> pd.Series:
    rows = session.execute(
        select(Observation.date, Observation.value)
        .where(Observation.keyword_id == keyword.id, Observation.source == source)
        .order_by(Observation.date)
    ).all()
    series = pd.Series({d: v for d, v in rows}, dtype=float)
    series.index = pd.to_datetime(series.index)
    return series.tail(days) if days else series
