"""Conector real a Wikimedia Pageviews API (externa a nuestra aplicación)."""
from __future__ import annotations

import datetime as dt
from urllib.parse import quote

import requests
from .. import config
from ..services import InvalidSourceData, SourceUnavailable
from .base import Connector, Point

BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"


class WikipediaConnector(Connector):
    name = "wikipedia"

    def __init__(self, project: str | None = None, user_agent: str | None = None, timeout: int = 20):
        self.project = project or config.WIKI_PROJECT
        self.headers = {"User-Agent": user_agent or config.WIKI_USER_AGENT}
        self.timeout = timeout

    def _url(self, term: str, start: dt.date, end: dt.date) -> str:
        article = quote(term.strip().replace(" ", "_"), safe="")
        return (
            f"{BASE}/{self.project}/all-access/user/{article}/daily/"
            f"{start:%Y%m%d}/{end:%Y%m%d}"
        )

    def fetch(self, term: str, start: dt.date, end: dt.date) -> list[Point]:
        try:
            resp = requests.get(self._url(term, start, end), headers=self.headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceUnavailable("No se puede contactar con Wikimedia") from exc
        if resp.status_code == 404:
            return []
        if resp.status_code != 200:
            raise SourceUnavailable("Wikimedia devolvió un error HTTP")
        try:
            items = resp.json()["items"]
            if not isinstance(items, list):
                raise ValueError("items no es una lista")
            points = []
            for item in items:
                day = dt.datetime.strptime(item["timestamp"][:8], "%Y%m%d").date()
                views = item["views"]
                if isinstance(views, bool) or not isinstance(views, int) or views < 0:
                    raise ValueError("Número de visitas inválido")
                points.append(Point(day, float(views)))
            return points
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidSourceData("Wikimedia devolvió registros inválidos") from exc
