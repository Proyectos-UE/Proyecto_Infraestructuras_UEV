"""Lee CSV exportados manualmente de Google Trends (sin scraping)."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .base import Point

_DATE_HEADERS = {"día", "dia", "semana", "mes", "day", "week", "month"}


def read_trends_csv(path: str | Path, strict: bool = False) -> list[Point]:
    """Lee una serie de Google Trends. strict=True rechaza filas defectuosas."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    start = next(
        (i for i, r in enumerate(rows) if r and r[0].strip().lower() in _DATE_HEADERS), None
    )
    if start is None:
        raise ValueError("No se encontró la cabecera de fechas en el CSV de Google Trends")

    points = []
    for line_number, row in enumerate(rows[start + 1 :], start=start + 2):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < 2 or not row[0].strip():
            if strict:
                raise ValueError(f"Fila incompleta en línea {line_number}")
            continue
        raw = row[1].strip()
        if raw == "<1":
            raw = "1"  # Google Trends utiliza '<1' para índices muy pequeños.
        try:
            value = float(raw)
            fecha = row[0].strip()
            if len(fecha) == 7 and fecha[4] == "-":
                fecha += "-01"  # Series mensuales con formato AAAA-MM.
            day = dt.date.fromisoformat(fecha[:10])
        except ValueError as exc:
            if strict:
                raise ValueError(f"Datos incorrectos en línea {line_number}") from exc
            continue
        points.append(Point(day, value))
    return points
