"""Conector opcional de PyTrends.

PyTrends está archivado y Google lo bloquea con frecuencia (HTTP 429), así que
este conector NUNCA debe romper el sistema: ante cualquier fallo devuelve [].
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from .base import Connector, Point

log = logging.getLogger(__name__)


class PyTrendsConnector(Connector):
    name = "pytrends"

    def __init__(self, geo: str = "ES", retries: int = 3, backoff: float = 5.0):
        self.geo = geo
        self.retries = retries
        self.backoff = backoff

    def fetch(self, term: str, start: dt.date, end: dt.date) -> list[Point]:
        try:
            from pytrends.request import TrendReq  # import tardío: es opcional
        except ImportError:
            log.info("pytrends no está instalado; se omite esta fuente")
            return []
        for attempt in range(1, self.retries + 1):
            try:
                client = TrendReq(hl="es-ES", tz=60)
                client.build_payload([term], timeframe=f"{start} {end}", geo=self.geo)
                df = client.interest_over_time()
                if df.empty:
                    return []
                return [Point(idx.date(), float(row[term])) for idx, row in df.iterrows()]
            except Exception as exc:  # noqa: BLE001 - fuente frágil, no debe tumbar el worker
                log.warning("PyTrends intento %s/%s falló: %s", attempt, self.retries, exc)
                time.sleep(self.backoff * attempt)
        return []
