"""Importa a la base de datos un CSV descargado manualmente de Google Trends."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trendwatch.connectors.google_trends_csv import read_trends_csv  # noqa: E402
from trendwatch.db import SessionLocal, init_db  # noqa: E402
from trendwatch.models import Keyword  # noqa: E402
from trendwatch.services import save_points, validar_puntos  # noqa: E402


def importar(session: Session, ruta: str | Path, termino: str) -> int:
    """Valida todo antes de escribir: una fila por término, fuente y fecha."""
    termino = termino.strip()
    if not 2 <= len(termino) <= 100:
        raise ValueError("El término debe tener entre 2 y 100 caracteres")
    puntos = read_trends_csv(ruta, strict=True)
    if not puntos:
        raise ValueError("El CSV no contiene registros válidos")
    validar_puntos(
        puntos,
        "google_trends_csv",
        min(p.date for p in puntos),
        max(p.date for p in puntos),
    )
    try:
        kw = session.scalar(select(Keyword).where(Keyword.term == termino))
        if kw is None:
            kw = Keyword(term=termino)
            session.add(kw)
            session.flush()
        cantidad = save_points(session, kw, "google_trends_csv", puntos)
        return cantidad
    except Exception:
        session.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description="Cargar CSV de Google Trends")
    parser.add_argument("archivo", help="Ruta del CSV exportado de Google Trends")
    parser.add_argument("producto", help="Término asociado al archivo CSV")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as session:
        cantidad = importar(session, args.archivo, args.producto)
    print(f"Se guardaron/actualizaron {cantidad} observaciones de {args.producto!r}")


if __name__ == "__main__":
    main()
