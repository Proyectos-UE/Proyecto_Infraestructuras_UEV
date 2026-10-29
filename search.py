"""Búsqueda libre de un término con fuentes GRATUITAS, agregada por meses.

- trends:    Google Trends (vía PyTrends). Cualquier término. Es interés RELATIVO (0-100),
             NO el número de búsquedas. Librería no oficial: Google puede bloquearla.
- wikipedia: visitas reales al artículo con ese título. Solo si el artículo existe.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from collections import defaultdict
from statistics import mean

import ingest

CACHE_TTL = 3600  # segundos: evita repetir peticiones a Google (y que nos bloquee)
_cache: dict[tuple, tuple[float, dict]] = {}


class SourceUnavailable(Exception):
    """La fuente no responde (bloqueo, sin conexión, librería no instalada)."""


class NoData(Exception):
    """La fuente responde, pero no tiene datos de ese término."""


def _timeframe(months: int) -> str:
    # Trends devuelve datos semanales hasta 5 años y mensuales con "all"
    if months <= 12:
        return "today 12-m"
    if months <= 60:
        return "today 5-y"
    return "all"


def google_trends_series(term: str, geo: str, timeframe: str, retries: int = 3, pause: float = 5.0):
    """Serie (fecha, valor 0-100) de Google Trends. Lanza SourceUnavailable si falla."""
    try:
        from pytrends.request import TrendReq
    except ImportError as exc:
        raise SourceUnavailable("pytrends no está instalado (pip install pytrends)") from exc
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            # No pasar retries/backoff_factor a TrendReq: rompe con urllib3 2.x
            client = TrendReq(hl="es-ES", tz=60)
            client.build_payload([term], timeframe=timeframe, geo=geo)
            frame = client.interest_over_time()
            if frame.empty:
                return []
            return [(index.date(), float(row[term])) for index, row in frame.iterrows()]
        except Exception as exc:  # noqa: BLE001 - fuente frágil
            last_error = exc
            if attempt < retries:
                time.sleep(pause * attempt)
    raise SourceUnavailable(f"Google Trends no responde ahora mismo ({last_error})")


def wikipedia_daily(term: str, start: dt.date, end: dt.date):
    """Serie diaria (fecha, visitas) del artículo de Wikipedia con ese título (usa la tubería de ingesta)."""
    user_agent = os.environ.get("WIKI_USER_AGENT")
    if not user_agent:
        raise SourceUnavailable("WIKI_USER_AGENT no está configurado")
    try:
        return sorted(ingest.get_points("wikipedia", term, start, end, user_agent).points.items())
    except (ingest.UpstreamError, ingest.QualityError) as exc:
        raise SourceUnavailable(str(exc)) from exc


def to_monthly(points, how: str, months: int, today: dt.date | None = None) -> list[dict]:
    """Agrupa puntos (fecha, valor) por mes: `sum` para visitas, `mean` para el índice de Trends."""
    today = today or dt.date.today()
    buckets: dict[tuple[int, int], list[float]] = defaultdict(list)
    for day, value in points:
        buckets[(day.year, day.month)].append(value)
    aggregate = sum if how == "sum" else mean
    return [
        {
            "month": f"{year}-{month:02d}",
            "value": round(aggregate(buckets[(year, month)]), 1),
            "partial": (year, month) == (today.year, today.month),  # el mes en curso está incompleto
        }
        for year, month in sorted(buckets)[-months:]
    ]


def _from_trends(term: str, months: int, geo: str) -> dict:
    points = google_trends_series(term, geo, _timeframe(months))
    if not points:
        raise NoData("Google Trends no tiene datos suficientes de ese término")
    return {
        "source": "trends",
        "unit": "interés relativo (0-100), NO es el número de búsquedas",
        "geo": geo or None,
        "months": to_monthly(points, "mean", months),
    }


def _from_wikipedia(term: str, months: int) -> dict:
    today = dt.date.today()
    first = today.replace(day=1)
    for _ in range(months - 1):
        first = (first - dt.timedelta(days=1)).replace(day=1)
    points = wikipedia_daily(term, first, today - dt.timedelta(days=1))
    if not points:
        raise NoData("No hay artículo de Wikipedia con ese título (o no tiene visitas registradas)")
    return {
        "source": "wikipedia",
        "unit": "visitas al artículo de Wikipedia (no son búsquedas)",
        "geo": None,
        "months": to_monthly(points, "sum", months),
    }


def get_monthly(term: str, months: int, geo: str, source: str) -> dict:
    """Devuelve la serie mensual. source = auto | trends | wikipedia.

    Lanza NoData si ninguna fuente tiene el término y SourceUnavailable si las fuentes fallan.
    """
    key = (term.lower(), months, geo, source)
    cached = _cache.get(key)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    result, unavailable, note = None, False, None
    if source in ("auto", "trends"):
        try:
            result = _from_trends(term, months, geo)
        except SourceUnavailable as exc:
            unavailable, note = True, str(exc)
        except NoData as exc:
            note = str(exc)
    if result is None and source in ("auto", "wikipedia"):
        try:
            result = _from_wikipedia(term, months)
            if note:
                result["note"] = f"Se usó Wikipedia porque: {note}"
        except SourceUnavailable as exc:
            unavailable, note = True, note or str(exc)
        except NoData as exc:
            note = note or str(exc)
    if result is None:
        if unavailable:
            raise SourceUnavailable(note)
        raise NoData(note or "Sin datos")

    result = {"query": term, "note": result.get("note"), **{k: v for k, v in result.items() if k != "note"}}
    _cache[key] = (time.time(), result)
    return result
