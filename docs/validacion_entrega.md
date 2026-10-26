# Comprobación de la entrega (22-10-2026)

Esta verificación se realizó con una copia de trabajo de la rama `test`,
respetando la rama `main` vacía y los cambios locales previos.

## Integración con Docker

Comandos desde la raíz del repositorio:

```bash
python scripts/preparar_config.py
# Elegir SOURCE_MODE=demo en .env, sin subir este archivo
docker compose config -q
docker compose up -d --build
docker compose ps
```

**Servicios iniciados:** `api`, `demo`, `worker`, `db` (PostgreSQL saludable)
y `dashboard`. El dashboard respondió HTTP 200 en `http://localhost:8501/`.
La API mostró la documentación en `http://localhost:8000/openapi.json`.
Esta comprobación HTTP no sustituye una revisión visual manual de Streamlit.

**Pruebas end-to-end:**

- `POST /watchlist` autorizado → HTTP 201.
- `POST /watchlist` con nombre vacío → HTTP 422.
- `POST /ingest` sin clave → HTTP 401.
- `POST /ingest` con clave → HTTP 200, 35 observaciones simuladas
  por producto, provenientes de un segundo servicio HTTP.
- Se repitió la ingesta y el número de filas siguió siendo **70** para
  los dos términos; no se insertaron duplicados.
- `GET /trends/mini%20proyectores?source=demo` devolvió 35 registros.
- `GET /trends/mini%20proyectores/spike?source=demo` detectó el
  pico **que habíamos incorporado a los datos sintéticos**.
- `GET /rankings/rising?source=demo` mostró ambos productos.
- `GET /trends/inexistente` → HTTP 404.
- `python -m trendwatch.worker --once` funciona con la fuente demo.

## Fuente real (Wikipedia)

Se ejecutó una ingesta puntual con `SOURCE_MODE=wikipedia`
hacia la API oficial Wikimedia Pageviews. Se almacenaron **90 observaciones**
reales del artículo `Taylor Swift`, recuperables por
`GET /trends/Taylor%20Swift?source=wikipedia`. El artículo correspondiente
a `mini proyectores` no existe o no devolvió visitas y se guardaron
0 observaciones de esa fuente, sin bloquear el proceso.

**Límite:** las visitas a Wikipedia no son búsquedas de Google ni ventas.

## Pruebas automatizadas y backtest

```bash
python -m pytest -q
python scripts/backtest.py --guardar
```

Resultado: **35 pruebas superadas** (una advertencia de deprecación en
`fastapi.testclient`). El backtest actual es **sintético**, semilla 42.
En la configuración base produjo TP=5, FP=0, FN=0, TN=5, anticipación
media artificial de 3,4 días. Esto NO acredita precisión comercial real.
Véanse `docs/backtest.md` y `notebooks/backtest_tendencias.ipynb`.

## Pendiente para fases posteriores

- Validación histórica con **productos reales y fechas documentadas**.
- Inspección visual manual completa de las interacciones de Streamlit.
- Despliegue en un proveedor de nube, si el profesor lo exige.
- Volver a vincular Google Trends como fuente principal, si se decide
  seguir literalmente el planteamiento original. El CSV está soportado
  como lector, pero no existe una ingesta automatizada de CSV al almacén.

## Actualización: importación de Google Trends con Python

Se añadió un script Python (`scripts/importar_trends_csv.py`) que carga en
PostgreSQL los CSV descargados manualmente. Se probó con un archivo CSV de
**tres registros de demostración** para `mini proyectores`, copiado al
contenedor API y consultado después por HTTP como fuente `google_trends_csv`.

Estas tres filas de ensayo **no son datos descargados realmente de Google
Trends**. Para analizarlos como fuente real es necesario descargar primero
el CSV auténtico desde la web de Google Trends y repetir el proceso del README.
El importador hace cumplir el rango 0-100, fechas sin duplicados y la
validación estricta de todas las filas. Las pruebas comprueban también la
recarga del mismo CSV, sin duplicar observaciones.

El notebook `notebooks/backtest_tendencias.ipynb` se ejecutó con Python 3.12
sin errores e incluyó una gráfica real de Wikipedia y otra de series
sintéticas; se detectaron 4 alertas en la serie real sin asociarlas a ventas
ni a eventos virales documentados.
