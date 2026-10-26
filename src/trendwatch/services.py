"""Reglas de validación, ingesta y consultas, compartidas por API y worker."""
from __future__ import annotations

import datetime as dt
import logging
import math

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .connectors.base import Connector, Point
from .models import Keyword, Observation

log = logging.getLogger(__name__)


class InvalidSourceData(Exception):
    """La API externa devolvió registros fuera del esquema permitido."""


class SourceUnavailable(Exception):
    """No ha sido posible obtener datos de la API externa."""


def validar_puntos(points: list[Point], source: str, start: dt.date, end: dt.date) -> None:
    if not isinstance(points, list):
        raise InvalidSourceData("Se esperaba una lista de registros")
    fechas = set()
    for p in points:
        if not isinstance(p, Point) or not isinstance(p.date, dt.date) or isinstance(p.date, dt.datetime):
            raise InvalidSourceData("La fecha de un registro no es válida")
        if p.date < start or p.date > end or p.date in fechas:
            raise InvalidSourceData("Fecha fuera de rango o duplicada en la fuente")
        fechas.add(p.date)
        if isinstance(p.value, bool) or not isinstance(p.value, (float, int)) or not math.isfinite(p.value) or p.value < 0:
            raise InvalidSourceData("El interés debe ser un número no negativo y finito")
        if source in ("demo", "pytrends", "google_trends_csv") and p.value > 100:
            raise InvalidSourceData("El índice relativo de interés no puede superar 100")


def save_points(session: Session, keyword: Keyword, source: str, points, commit: bool = True) -> int:
    """Inserta o actualiza observaciones; reutiliza la misma fecha y fuente."""
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
    if commit:
        session.commit()
    return written


def ingest_keyword(session: Session, keyword: Keyword, connectors: list[Connector], days: int) -> dict[str, int]:
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    validos = []
    for conn in connectors:
        points = conn.fetch(keyword.term, start, end)
        validar_puntos(points, conn.name, start, end)
        validos.append((conn.name, points))
    try:
        result = {}
        for name, points in validos:
            result[name] = save_points(session, keyword, name, points, commit=False)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise


def get_series(session: Session, keyword: Keyword, source: str, days: int | None = None) -> pd.Series:
    rows = session.execute(
        select(Observation.date, Observation.value)
        .where(Observation.keyword_id == keyword.id, Observation.source == source)
        .order_by(Observation.date)
    ).all()
    series = pd.Series({d: v for d, v in rows}, dtype=float)
    series.index = pd.to_datetime(series.index)
    return series.tail(days) if days else series
