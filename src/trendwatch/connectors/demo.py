"""Conector a una API simulada independiente, por HTTP real."""
import datetime as dt
import requests
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from .. import config
from ..services import InvalidSourceData, SourceUnavailable
from .base import Connector, Point


class DemoRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha: dt.date
    interes: int = Field(ge=0, le=100, strict=True)


class DemoConnector(Connector):
    name = "demo"

    def fetch(self, term: str, start: dt.date, end: dt.date) -> list[Point]:
        try:
            respuesta = requests.get(
                config.DEMO_SOURCE_URL,
                params={"term": term, "start": start.isoformat(), "end": end.isoformat()},
                timeout=5,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise SourceUnavailable("La API externa simulada no responde") from exc
        if respuesta.status_code != 200:
            raise SourceUnavailable("La API externa simulada devolvió un error HTTP")
        try:
            registros = TypeAdapter(list[DemoRecord]).validate_python(respuesta.json())
        except (ValueError, ValidationError) as exc:
            raise InvalidSourceData("La API externa simulada devolvió datos inválidos") from exc
        return [Point(r.fecha, float(r.interes)) for r in registros]
