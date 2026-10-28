"""Genera data/products.json con DATOS REALES de visitas de Wikipedia.

Uso (necesita Internet):
    python fetch_data.py            # últimos 90 días
    python fetch_data.py 180        # últimos 180 días

Edita la lista PRODUCTS para vigilar vuestros propios productos. Si el título del
artículo de Wikipedia no coincide con el nombre, ponedlo como tercer valor.
Los productos sin datos se omiten y se avisa por pantalla.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

# (nombre, categoría) o (nombre, categoría, título exacto en Wikipedia)
PRODUCTS = [
    ("Freidora de aire", "hogar"),
    ("Aspiradora robótica", "hogar"),
    ("Domótica", "hogar"),
    ("Altavoz inteligente", "hogar"),
    ("Reloj inteligente", "tecnologia"),
    ("Realidad virtual", "tecnologia"),
    ("Impresión 3D", "tecnologia"),
    ("Inteligencia artificial", "tecnologia"),
    ("Tarjeta gráfica", "tecnologia"),
    ("Patinete eléctrico", "movilidad"),
    ("Bicicleta eléctrica", "movilidad"),
    ("Vehículo eléctrico", "movilidad"),
    ("Vehículo autónomo", "movilidad"),
    ("Pulsera de actividad", "salud"),
    ("Ayuno intermitente", "salud"),
    ("Creatina", "salud"),
    ("Kombucha", "alimentacion"),
    ("Pickleball", "deporte"),
    ("Pádel", "deporte"),
    ("Videoconsola", "ocio"),
]

PROJECT = "es.wikipedia"
BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
OUT_FILE = Path(__file__).parent / "data" / "products.json"


def fetch_series(title: str, start: dt.date, end: dt.date, user_agent: str) -> list[dict]:
    """Visitas diarias de un artículo. Lista vacía si no hay datos o falla la red."""
    article = quote(title.strip().replace(" ", "_"), safe="")
    url = f"{BASE}/{PROJECT}/all-access/user/{article}/daily/{start:%Y%m%d}/{end:%Y%m%d}"
    try:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=20)
    except requests.RequestException as exc:
        print(f"  ! sin conexión: {exc}")
        return []
    if resp.status_code != 200:
        return []
    return [
        {
            "date": dt.datetime.strptime(item["timestamp"][:8], "%Y%m%d").date().isoformat(),
            "value": float(item["views"]),
        }
        for item in resp.json().get("items", [])
    ]


def main(days: int = 90) -> None:
    user_agent = os.environ.get(
        "WIKI_USER_AGENT", "TrendWatch/0.1 (proyecto universitario; contacto: tu_email@ejemplo.com)"
    )
    end = dt.date.today() - dt.timedelta(days=1)  # el día de hoy aún está incompleto
    start = end - dt.timedelta(days=days)
    records = []
    for entry in PRODUCTS:
        name, category = entry[0], entry[1]
        title = entry[2] if len(entry) > 2 else name
        series = fetch_series(title, start, end, user_agent)
        if not series:
            print(f"SIN DATOS  {name} (probad con el título exacto de Wikipedia)")
            continue
        records.append(
            {"id": len(records) + 1, "name": name, "category": category,
             "source": "wikipedia", "series": series}
        )
        print(f"OK         {name}: {len(series)} días")
    if not records:
        sys.exit("No se ha podido descargar nada; no se modifica data/products.json")
    OUT_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nEscrito {OUT_FILE} con {len(records)} productos")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 90)
