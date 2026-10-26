"""Ingesta una vez (--once) o repetidamente (sin argumento)."""
from __future__ import annotations
import argparse
import logging
import time
from sqlalchemy import select
from . import config
from .connectors.demo import DemoConnector
from .connectors.pytrends_conn import PyTrendsConnector
from .connectors.wikipedia import WikipediaConnector
from .db import SessionLocal, init_db
from .models import Keyword
from .services import ingest_keyword

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(name)s: %(message)s")
log = logging.getLogger("worker")


def build_connectors():
    if config.SOURCE_MODE == "demo":
        return [DemoConnector()]
    if config.SOURCE_MODE != "wikipedia":
        raise ValueError("SOURCE_MODE debe ser wikipedia o demo")
    conectores = [WikipediaConnector()]
    if config.ENABLE_PYTRENDS:
        conectores.append(PyTrendsConnector())
    return conectores


def run_once() -> dict:
    init_db()
    resultado = {}
    with SessionLocal() as session:
        for keyword in list(session.scalars(select(Keyword).order_by(Keyword.term))):
            resultado[keyword.term] = ingest_keyword(session, keyword, build_connectors(), config.HISTORY_DAYS)
            log.info("Ingestado %s: %s", keyword.term, resultado[keyword.term])
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta de tendencias desde la API externa")
    parser.add_argument("--once", action="store_true", help="Ejecutar una vez y terminar")
    args = parser.parse_args()
    if args.once:
        print(run_once())
        return
    while True:
        try:
            run_once()
        except Exception:
            log.exception("Fallo en la ingesta; se reintentará en el siguiente ciclo")
        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
