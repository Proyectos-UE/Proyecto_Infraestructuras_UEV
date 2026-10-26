"""Conector de la Wikimedia Pageviews API (oficial, gratuita, sin clave).

Doc: https://wikimedia.org/api/rest_v1/#/Pageviews%20data
"""
from __future__ import annotations

import datetime as dt
import logging
from urllib.parse import quote

import requests

from .. import config
from .base import Connector, Point

log = logging.getLogger(__name__)

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
        url = self._url(term, start, end)
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
        except requests.RequestException as exc:
            log.warning("Wikipedia no disponible para %r: %s", term, exc)
            return []
        if resp.status_code == 404:  # artículo inexistente o sin datos en el rango
            return []
        if resp.status_code != 200:
            log.warning("Wikipedia devolvió %s para %r", resp.status_code, term)
            return []
        points = []
        for item in resp.json().get("items", []):
            day = dt.datetime.strptime(item["timestamp"][:8], "%Y%m%d").date()
            points.append(Point(day, float(item["views"])))
        return points
