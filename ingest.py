"""Proceso de ingesta: API externa -> validación -> reglas -> informe.

Fuente externa: Wikimedia Pageviews API (visitas diarias a artículos de Wikipedia).
Hay dos "transportes" que alimentan EXACTAMENTE la misma tubería de validación:

  - "wikipedia"  : API real de Wikimedia (necesita Internet y WIKI_USER_AGENT).
  - "simulated"  : API simulada con el mismo formato de respuesta (reproducible sin Internet).

Etapas
  1. EXTRACCIÓN  fetch_raw()      pide los datos a la API externa (con timeout y 1 reintento).
  2. VALIDACIÓN  validate()       cada registro se valida con Pydantic; los inválidos se rechazan uno a uno.
  3. REGLAS      validate() +     ventana de fechas, sin duplicados y calidad mínima
                 check_quality()  (si más del 20 % de los registros son inválidos NO se carga nada).
  4. CARGA       (en main.py)     fusión idempotente en el catálogo + informe + registro de la ejecución.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from urllib.parse import quote

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROJECT = "es.wikipedia"
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
TIMEOUT_SECONDS = 15
MAX_REJECTED_RATIO = 0.20  # regla de calidad
MAX_SAMPLES = 5  # cuántos motivos de rechazo se muestran en el informe

# Productos de la API simulada que terminan con un pico, para poder enseñar el detector
SIMULATED_SPIKES = {"Freidora de aire": 3.2, "Pickleball": 3.0}


class UpstreamError(Exception):
    """La API externa no responde o devuelve algo ilegible (la API de TrendWatch responde 502)."""


class QualityError(Exception):
    """Demasiados registros inválidos: no se carga nada (la API de TrendWatch responde 422)."""


class WikimediaItem(BaseModel):
    """Un registro de la respuesta de Wikimedia. Se ignoran los campos que no usamos."""

    model_config = ConfigDict(extra="ignore")

    timestamp: str = Field(pattern=r"^\d{10}$")  # AAAAMMDDHH, p. ej. 2026101500
    views: int = Field(ge=0)


@dataclass
class Validated:
    points: dict[dt.date, float] = field(default_factory=dict)
    received: int = 0
    rejected: int = 0
    samples: list[str] = field(default_factory=list)


def window(days: int, today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Ventana de ingesta: los `days` días hasta AYER (el día en curso está incompleto)."""
    end = (today or dt.date.today()) - dt.timedelta(days=1)
    return end - dt.timedelta(days=days - 1), end


# ---------- 1. Extracción ----------
def simulate_wikimedia(title: str, start: dt.date, end: dt.date) -> dict:
    """API simulada: misma estructura que Wikimedia y datos deterministas por título."""
    rng = random.Random(title)
    level = rng.choice([30, 60, 120, 250, 500])
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]
    items = []
    for index, day in enumerate(days):
        views = round(level * (1.08 if day.weekday() >= 5 else 1.0) * rng.uniform(0.9, 1.1))
        if index == len(days) - 1 and title in SIMULATED_SPIKES:
            views = round(level * SIMULATED_SPIKES[title])
        items.append({
            "project": PROJECT, "article": title.replace(" ", "_"), "granularity": "daily",
            "timestamp": f"{day:%Y%m%d}00", "access": "all-access", "agent": "user", "views": views,
        })
    return {"items": items}


def fetch_raw(source: str, title: str, start: dt.date, end: dt.date, user_agent: str | None = None) -> dict:
    """Pide los datos crudos a la API externa. Lanza UpstreamError si falla."""
    if source == "simulated":
        return simulate_wikimedia(title, start, end)
    if source != "wikipedia":
        raise ValueError(f"Unknown source: {source}")

    article = quote(title.strip().replace(" ", "_"), safe="")
    url = f"{BASE}/{PROJECT}/all-access/user/{article}/daily/{start:%Y%m%d}/{end:%Y%m%d}"
    last_error = "sin respuesta"
    for _attempt in (1, 2):  # un reintento ante fallos de red o errores 5xx
        try:
            resp = requests.get(url, headers={"User-Agent": user_agent or ""}, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = f"sin conexión con Wikimedia ({exc.__class__.__name__})"
            continue
        if resp.status_code == 404:  # el artículo no existe o no tiene datos en el rango
            return {"items": []}
        if resp.status_code >= 500:
            last_error = f"Wikimedia devolvió {resp.status_code}"
            continue
        if resp.status_code != 200:
            raise UpstreamError(f"Wikimedia devolvió {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise UpstreamError("Wikimedia devolvió algo que no es JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise UpstreamError("Wikimedia devolvió un formato inesperado")
        return data
    raise UpstreamError(last_error)


# ---------- 2 y 3. Validación y reglas ----------
def validate(raw: dict, start: dt.date, end: dt.date) -> Validated:
    """Valida registro a registro. Reglas: formato correcto, dentro de la ventana, sin fechas repetidas."""
    result = Validated()
    for item in raw.get("items", []):
        result.received += 1
        reason = None
        day = None
        try:
            record = WikimediaItem.model_validate(item)
            day = dt.datetime.strptime(record.timestamp[:8], "%Y%m%d").date()
        except ValidationError as exc:
            first = exc.errors()[0]
            reason = f"registro inválido ({first['loc'][0] if first['loc'] else 'formato'}: {first['msg']})"
        except ValueError:
            reason = "fecha imposible"
        if reason is None and not (start <= day <= end):
            reason = f"fecha {day} fuera de la ventana {start}..{end}"
        if reason is None and day in result.points:
            reason = f"fecha {day} repetida"
        if reason:
            result.rejected += 1
            if len(result.samples) < MAX_SAMPLES:
                result.samples.append(reason)
        else:
            result.points[day] = float(record.views)
    return result


def check_quality(result: Validated) -> None:
    """Regla de calidad: si se rechaza más del 20 % no se acepta la tanda entera."""
    if result.received and result.rejected / result.received > MAX_REJECTED_RATIO:
        raise QualityError(
            f"{result.rejected} de {result.received} registros inválidos "
            f"(el máximo permitido es {MAX_REJECTED_RATIO:.0%})"
        )


def get_points(source: str, title: str, start: dt.date, end: dt.date, user_agent: str | None = None) -> Validated:
    """Extrae, valida y aplica las reglas. Devuelve los puntos aceptados y las estadísticas."""
    result = validate(fetch_raw(source, title, start, end, user_agent), start, end)
    check_quality(result)
    return result
