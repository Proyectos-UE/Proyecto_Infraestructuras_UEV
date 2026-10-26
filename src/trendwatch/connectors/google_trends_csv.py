"""Lee CSVs exportados a mano desde trends.google.es (botón de descarga).

Es la vía fiable para el histórico y el backtest: no depende de scraping.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .base import Point

_DATE_HEADERS = {"día", "dia", "semana", "mes", "day", "week", "month"}


def read_trends_csv(path: str | Path) -> list[Point]:
    """Devuelve los puntos de la primera columna de valores del CSV."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    start = next(
        (i for i, r in enumerate(rows) if r and r[0].strip().lower() in _DATE_HEADERS), None
    )
    if start is None:
        raise ValueError("No se encontró la cabecera de fechas en el CSV de Google Trends")
    points = []
    for row in rows[start + 1 :]:
        if len(row) < 2 or not row[0].strip():
            continue
        raw = row[1].strip().replace("<", "")  # Trends escribe "<1" para valores muy bajos
        try:
            value = float(raw)
            day = dt.date.fromisoformat(row[0].strip()[:10])
        except ValueError:
            continue
        points.append(Point(day, value))
    return points
