"""Proceso que recoge datos periódicamente: `python -m trendwatch.worker`."""
from __future__ import annotations

import logging
import time

from sqlalchemy import select

from . import config
from .connectors.pytrends_conn import PyTrendsConnector
from .connectors.wikipedia import WikipediaConnector
from .db import SessionLocal, init_db
from .models import Keyword
from .services import ingest_keyword

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")


def build_connectors():
    connectors = [WikipediaConnector()]
    if config.ENABLE_PYTRENDS:
        connectors.append(PyTrendsConnector())
    return connectors


def run_once() -> None:
    connectors = build_connectors()
    with SessionLocal() as session:
        for kw in session.scalars(select(Keyword)):
            ingest_keyword(session, kw, connectors, config.HISTORY_DAYS)


def main() -> None:
    init_db()
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001 - el worker no debe morir
            log.exception("Fallo en la ingesta")
        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
