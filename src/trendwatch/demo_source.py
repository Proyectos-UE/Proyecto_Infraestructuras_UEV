"""API HTTP externa simulada para ejecutar una demo sin Internet."""
import datetime as dt
from typing import Literal
from fastapi import FastAPI, HTTPException, Query

app = FastAPI(title="Fuente externa simulada de tendencias", version="1.0")


@app.get("/datos")
def datos(
    term: str = Query(min_length=2, max_length=100),
    start: dt.date | None = None,
    end: dt.date | None = None,
    escenario: Literal["normal", "invalidos", "no_disponible"] = "normal",
):
    if escenario == "no_disponible":
        raise HTTPException(503, "La fuente no está disponible")
    if escenario == "invalidos":
        return [{"fecha": "fecha-incorrecta", "interes": 150}]
    fin = end or dt.date.today()
    inicio = start or fin - dt.timedelta(days=34)
    base = 20 + sum(ord(c) for c in term) % 20
    resultado = []
    for i in range(35):
        fecha = fin - dt.timedelta(days=34 - i)
        if fecha >= inicio:
            valor = base + (i % 4)
            if i == 34:
                valor = min(100, base + 55)
            resultado.append({"fecha": fecha.isoformat(), "interes": valor})
    return resultado
