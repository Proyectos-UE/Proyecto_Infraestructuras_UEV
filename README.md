# TrendWatch – Detección temprana de tendencias de mercado

Servicio en la nube que vigila productos y nichos (watchlist) y avisa cuando su
interés se dispara, antes de que se vuelvan virales.

**Equipo:** Pablo Díaz · Eduardo Caicedo · Jordi Aguado · Alessandro Matos
**Asignatura:** Infraestructuras y Computación en la Nube – Grado en Ciencia de Datos

## Cómo funciona

1. El usuario añade términos a la **watchlist** (API o dashboard).
2. Un **worker** recoge cada día el interés de cada término desde varias fuentes y lo guarda en la base de datos.
3. Un **detector** compara el último valor con la media móvil histórica (z-score + crecimiento) y marca los picos.
4. La **API REST** y el **dashboard** exponen series, picos y un ranking de nichos en ascenso.

Fuentes de datos y sus limitaciones: [`docs/fuentes_de_datos.md`](docs/fuentes_de_datos.md).
Arquitectura y UML: [`docs/arquitectura.md`](docs/arquitectura.md).
Planificación y riesgos: [`docs/planificacion.md`](docs/planificacion.md).

## Arranque rápido

### Con Docker (recomendado)

```bash
cp .env.example .env        # edita WIKI_USER_AGENT con tu email
docker compose up --build
```

- API + documentación interactiva: http://localhost:8000/docs
- Dashboard: http://localhost:8501

### En local (sin Docker)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export PYTHONPATH=src                                # Windows: set PYTHONPATH=src
uvicorn trendwatch.api.main:app --reload             # API (usa SQLite por defecto)
python -m trendwatch.worker                          # worker, en otra terminal
streamlit run dashboard/app.py                       # dashboard (pip install -r dashboard/requirements.txt)
pytest                                               # tests
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del servicio |
| GET | `/watchlist` | Lista de términos vigilados |
| POST | `/watchlist` | Añadir término `{"term": "air fryer"}` |
| DELETE | `/watchlist/{term}` | Quitar término |
| GET | `/trends/{term}?source=&days=` | Serie temporal de interés |
| GET | `/trends/{term}/spike` | ¿Hay pico ahora? (z-score, crecimiento) |
| GET | `/rankings/rising` | Términos con mayor crecimiento |

## Estructura del repositorio

```
├── src/trendwatch/
│   ├── api/main.py              # API FastAPI
│   ├── connectors/              # Una clase por fuente de datos
│   │   ├── base.py              #   interfaz común
│   │   ├── wikipedia.py         #   Wikimedia Pageviews API (fuente principal)
│   │   ├── google_trends_csv.py #   CSV exportado de Google Trends (histórico)
│   │   └── pytrends_conn.py     #   PyTrends (opcional, frágil)
│   ├── detection/spike.py       # Detector de picos
│   ├── models.py, db.py         # Base de datos (SQLAlchemy)
│   ├── services.py              # Ingesta y consultas
│   └── worker.py                # Recogida periódica de datos
├── dashboard/                   # Streamlit
├── tests/                       # pytest
├── notebooks/                   # Exploración y backtest
├── data/raw/                    # CSVs descargados (no se versionan)
├── docs/                        # Documentación de la entrega
├── .github/workflows/ci.yml     # Tests + build Docker en cada PR
├── Dockerfile, docker-compose.yml
└── CONTRIBUTING.md              # Cómo trabajamos en equipo
```

## Estado

- [x] Esqueleto del proyecto, API, detector, conectores, Docker y CI
- [ ] Backtest con productos que fueron virales (`notebooks/`)
- [ ] Despliegue en la nube
- [ ] Fuentes adicionales (YouTube, Reddit)
