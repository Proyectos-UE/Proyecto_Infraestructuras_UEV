"""Interfaz común de los conectores de datos.

Añadir una fuente nueva = crear una clase que herede de Connector.
El resto del sistema no cambia.
"""
from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    date: dt.date
    value: float


class Connector(ABC):
    name: str

    @abstractmethod
    def fetch(self, term: str, start: dt.date, end: dt.date) -> list[Point]:
        """Devuelve la serie diaria del término. Lista vacía si no hay datos."""
