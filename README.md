# TrendWatch – Detección temprana de tendencias de mercado

Proyecto de **Infraestructuras y Computación en la Nube**, Grado en Ciencia de Datos.
Equipo: Pablo Díaz, Eduardo Caicedo, Jordi Aguado y Alessandro Matos.

TrendWatch permite registrar productos en una lista de vigilancia, recoger datos de interés por HTTP, almacenar su histórico y detectar picos con un **z-score** y crecimiento respecto a la media móvil. No predice ventas ni cantidades de compras: identifica señales de atención.

## Mapa rápido del repositorio

| Carpeta | Contenido |
|---|---|
| [src/trendwatch/](src/trendwatch/) | API FastAPI, modelos, conectores, worker y detector. |
| [dashboard/](dashboard/) | Panel de visualización Streamlit. |
| [scripts/](scripts/) | Configuración, importación y backtest en Python. |
| [tests/](tests/) | Pruebas automáticas y casos de error. |
| [notebooks/](notebooks/README.md) | Cuadernos de análisis separados de la aplicación. |
| [docs/](docs/README.md) | Arquitectura, fuentes, planificación y validación. |
| [data/raw/](data/raw/) | Datos CSV locales no versionados. |

La configuración de Docker y las dependencias quedan en la raíz para que los comandos de esta guía funcionen sin mover rutas.

## 1. Qué se entrega

- **API REST FastAPI** con documentación OpenAPI automática: `/docs` y `/openapi.json`.
- **Lectura pública y escritura administrativa**: las operaciones que cambian datos requieren `X-API-Key` (sin clave o errónea → 401; sin configurar la clave → 503).
- **Datos validados**: los términos tienen entre 2 y 100 caracteres; las series de la API simulada tienen fecha ISO e interés entero entre 0 y 100. Se rechazan fechas duplicadas, valores inválidos y datos fuera del intervalo.
- **Ingesta externa real** con la API de Wikimedia Pageviews; también se proporciona un **segundo servidor HTTP simulado** para reproducir todos los pasos sin Internet.
- **Almacenamiento** con SQLAlchemy: SQLite local o PostgreSQL con Docker; un término/fuente/fecha es único y la ingesta repetida actualiza, no duplica.
- **Worker**, dashboard Streamlit, pruebas de `pytest`, Docker y GitHub Actions.

**Fuentes:** Wikimedia mide visitas a artículos (no búsquedas). Google Trends se conserva como fuente de CSV histórico y PyTrends es opcional; su utilización no se confunde con la de Wikimedia. Ver `docs/fuentes_de_datos.md`.

## 2. Instalación en local (Python 3.10+)

Abre la terminal en la carpeta raíz del repositorio:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/preparar_config.py
```

En algunos Mac, usa `/opt/homebrew/bin/python3 -m venv .venv` para evitar el Python 3.9 del sistema. `preparar_config.py` crea **solo si no existe** un archivo `.env` con una clave API y contraseña de PostgreSQL aleatorias. **No se debe subir `.env` a Git.**

Para una demo reproducible sin Internet, edita en `.env`:

```ini
SOURCE_MODE=demo
```

Inicia **dos terminales** en la carpeta del proyecto (activando el entorno virtual en cada una):

**Terminal A, fuente externa simulada (puerto 8001):**

```bash
source .venv/bin/activate
PYTHONPATH=src python -m uvicorn trendwatch.demo_source:app --port 8001
```

**Terminal B, API principal (puerto 8000):**

```bash
source .venv/bin/activate
PYTHONPATH=src python -m uvicorn trendwatch.api.main:app --port 8000
```

Abre http://127.0.0.1:8000/docs. La fuente independiente tiene su propia documentación en http://127.0.0.1:8001/docs.

Alternativa con una API externa **real**: deja `SOURCE_MODE=wikipedia` en `.env`; no necesitas iniciar la terminal A. La API consulta Wikimedia por HTTP y el `WIKI_USER_AGENT` debe identificar al proyecto. Las visitas a Wikipedia no equivalen al volumen de búsquedas de Google Trends.

## 3. Endpoints y niveles de acceso

| Método | Ruta | Función | Permiso |
|---|---|---|---|
| GET | `/health` | Comprobar estado | Público |
| GET | `/watchlist` | Listar productos vigilados | Público |
| POST | `/watchlist` | Añadir producto con JSON `{"term":"mini proyectores"}` | Administrador |
| DELETE | `/watchlist/{term}` | Eliminar un producto | Administrador |
| POST | `/ingest` | Consultar la fuente HTTP externa y guardar sus datos | Administrador |
| GET | `/trends/{term}?source=demo&days=90` | Ver serie temporal | Público |
| GET | `/trends/{term}/spike?source=demo` | Detectar pico actual | Público |
| GET | `/rankings/rising?source=demo` | Ranking de tendencias | Público |

La API usa Pydantic para validar peticiones y SQLAlchemy para persistir. Errores esperados: **401** sin autorización, **404** producto inexistente, **409** duplicado o histórico insuficiente, **422** entrada incorrecta, **502** respuesta externa inválida y **503** fuente externa caída o administración sin configurar.

En `/docs`, pulsar **Authorize** para introducir la clave de `.env` y probar los endpoints protegidos.

## 4. Ejemplos reproducibles con curl

Con ambos servidores en marcha y `SOURCE_MODE=demo`:

```bash
# 1. Consulta correcta sin permisos (HTTP 200)
curl -i http://127.0.0.1:8000/health

# 2. Error de acceso: sin clave (HTTP 401)
curl -i -X POST http://127.0.0.1:8000/ingest

# 3. Cargar la clave privada local sin copiarla a los ejemplos
export API_KEY=$(sed -n 's/^API_KEY=//p' .env)

# 4. Dar de alta un producto (HTTP 201)
curl -i -X POST http://127.0.0.1:8000/watchlist \
  -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \
  -d '{"term":"mini proyectores"}'

# 5. Error por datos inválidos (HTTP 422)
curl -i -X POST http://127.0.0.1:8000/watchlist \
  -H 'Content-Type: application/json' -H "X-API-Key: $API_KEY" \
  -d '{"term":""}'

# 6. Ingesta real por HTTP desde el servicio externo (HTTP 200)
curl -i -X POST http://127.0.0.1:8000/ingest -H "X-API-Key: $API_KEY"

# 7. Repetir la ingesta: actualiza los datos sin crear duplicados
curl -i -X POST http://127.0.0.1:8000/ingest -H "X-API-Key: $API_KEY"

# 8. Consultar resultados
curl 'http://127.0.0.1:8000/trends/mini%20proyectores?source=demo'
curl 'http://127.0.0.1:8000/trends/mini%20proyectores/spike?source=demo'
curl 'http://127.0.0.1:8000/rankings/rising?source=demo'

# 9. Producto que no existe (HTTP 404)
curl -i http://127.0.0.1:8000/trends/inexistente
```

La respuesta de `POST /ingest` indica los términos procesados y el número de registros recibidos por fuente. Si se repite, no aparecen duplicados en la base de datos: se actualizan las mismas fechas.

## 5. Proceso de ingesta (reglas exactas)

1. **Solicitar**: la API exige la clave `X-API-Key` antes de hacer cualquier consulta externa. El modo de fuente se define en configuración del servidor, no por el usuario.
2. **Extraer**: el conector hace una petición HTTP GET a Wikimedia o al servicio independiente de demostración, con tiempo máximo de espera. El worker utiliza los mismos conectores.
3. **Validar**: para la fuente demo se exige un JSON de registros `{ "fecha": "AAAA-MM-DD", "interes": 45 }` con valores entre 0 y 100. Se valida además el intervalo, las fechas duplicadas y números no negativos y finitos. Wikimedia devuelve `timestamp` y `views` (visitas absolutas).
4. **Controlar errores**: JSON malformado → 502; fuente caída o HTTP no válido → 503. Las observaciones del término no se escriben si alguna validación falla.
5. **Guardar**: se inserta o actualiza una observación por combinación de término, fuente y fecha. Se hace un `commit` una vez validado el lote del término.
6. **Consultar**: las rutas `/trends`, `/spike` y `/rankings/rising` muestran los datos y el indicador calculado.

**Otra forma de hacer la ingesta una sola vez** (siempre desde la raíz y con la configuración cargada):

```bash
source .venv/bin/activate
PYTHONPATH=src python -m trendwatch.worker --once
```

Sin `--once`, el worker procesa los términos de la watchlist periódicamente según `POLL_INTERVAL_SECONDS` (por defecto, 24 horas).

**Prueba manual de errores de fuente:** con `SOURCE_MODE=demo`, modifica temporalmente `DEMO_SOURCE_URL` en `.env` para terminar en `?escenario=invalidos` (respuesta 502), o en `?escenario=no_disponible` (respuesta 503), reinicia la API, y repite `POST /ingest`. Restaura después la URL sin parámetros. Para un error de red, detén temporalmente el simulador y vuelve a hacer la petición.

## 6. Pruebas automáticas

```bash
source .venv/bin/activate
PYTHONPATH=src python -m pytest -q
```

Prueban consultas, documentación OpenAPI, autenticación ausente/incorrecta, administrador sin configurar, operaciones autorizadas, validaciones 422, inexistentes 404, duplicados 409, ingesta 200, errores externos 502/503, parseo de Wikimedia y CSV de Google Trends, y detección de picos. **No es necesario iniciar servidores** para ejecutar los tests: las respuestas HTTP externas se simulan.

## 7. Docker: API, base de datos, worker y panel

```bash
python scripts/preparar_config.py
# Si prefieres la demo, cambia SOURCE_MODE=wikipedia por SOURCE_MODE=demo en .env
docker compose up --build
```

- API: http://localhost:8000/docs
- Panel Streamlit: http://localhost:8501
- PostgreSQL se ejecuta dentro de Docker con credenciales leídas de `.env`.
- `demo` es un servicio independiente accesible a API/worker dentro de la red Docker.
- Para una ingesta puntual en Docker: `docker compose exec worker python -m trendwatch.worker --once`.

**Seguridad:** la clave API y contraseña de PostgreSQL se generan localmente y no aparecen en el repositorio. Los endpoints de lectura son públicos por diseño; los de escritura necesitan clave. No se deben reutilizar estos ejemplos como configuración de producción sin HTTPS, redes privadas, rotación de secretos y controles de acceso adicionales.

## 8. Estructura técnica

```text
src/trendwatch/api/main.py           API y OpenAPI
src/trendwatch/connectors/          Conectores de APIs externas
src/trendwatch/demo_source.py       Servidor HTTP externo simulado
src/trendwatch/services.py          Validación, ingesta y consultas
src/trendwatch/detection/spike.py   Detector de picos
src/trendwatch/worker.py            Ingesta programada o puntual
src/trendwatch/db.py, models.py     Base de datos
dashboard/                           Panel Streamlit
tests/                               Pruebas de casos buenos, malos y seguridad
scripts/preparar_config.py          Generación local de secretos
docs/                                Arquitectura, fuentes y planificación
.github/workflows/ci.yml            Pruebas y compilación Docker en cada PR
```

Las guías de arquitectura, fuentes y planificación están agrupadas en el [índice de documentación](docs/README.md). El backtest reproducible de la sección siguiente ya está implementado; quedan pendientes su validación con casos reales, el despliegue en nube y la ampliación de fuentes.

## 9. Validación integral y backtest reproducible

La verificación con Docker, casos HTTP, PostgreSQL e ingesta desde Wikimedia se documenta en [`docs/validacion_entrega.md`](docs/validacion_entrega.md).

Para generar los resultados reproducibles del detector: `python scripts/backtest.py --guardar`. El notebook está en [`notebooks/backtest_tendencias.ipynb`](notebooks/backtest_tendencias.ipynb). Instala `requirements-dev.txt` para disponer de Matplotlib. **El backtest con cinco picos y cinco controles emplea datos artificiales: no demuestra predicción real de ventas ni viralidad.** Véase [`docs/backtest.md`](docs/backtest.md).

### Importar CSV de Google Trends con Python

Si el profesor quiere observar la fuente propuesta originalmente (Google
Trends), descarga manualmente desde trends.google.es el CSV de un término y
ejecuta desde la raíz:

```bash
source .venv/bin/activate
PYTHONPATH=src python scripts/importar_trends_csv.py data/raw/archivo.csv "mini proyectores"
```

Si ejecutas la API en Docker, usa las siguientes instrucciones para importar
en **la misma base de datos PostgreSQL**:

```bash
docker compose cp data/raw/archivo.csv api:/tmp/trends.csv
docker compose exec api python scripts/importar_trends_csv.py /tmp/trends.csv "mini proyectores"
```

El importador valida fechas e índices (0-100), rechaza filas mal formadas,
fechas repetidas y registros fuera de rango y evita duplicados en la base de
datos. Después se consulta con
`GET /trends/mini%20proyectores?source=google_trends_csv`.

El CSV se obtiene manualmente; **no hay una API automática oficial de Google
Trends conectada a este importador**. Los números de Google Trends son índices
relativos, no cantidades exactas de búsquedas.
