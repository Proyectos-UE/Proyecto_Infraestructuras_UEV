"""TrendWatch API: detección temprana de picos de interés en productos y nichos."""
import datetime as dt
import json
import logging
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, Security
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

load_dotenv()  # lee el archivo .env si existe (nunca pisa variables ya definidas)

import ingest  # noqa: E402
import search  # noqa: E402
from spike import analyze  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("trendwatch")

# ======================================================================
# 1. Configuración y secretos (todo por variables de entorno, ver .env.example)
# ======================================================================
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
INGEST_API_KEY = os.environ.get("INGEST_API_KEY") or None  # opcional: clave con permisos mínimos
if not ADMIN_API_KEY:
    raise RuntimeError("ADMIN_API_KEY is required")
if INGEST_API_KEY and INGEST_API_KEY == ADMIN_API_KEY:
    raise RuntimeError("INGEST_API_KEY must be different from ADMIN_API_KEY")

DATA_FILE = Path(os.environ.get("DATA_FILE", Path(__file__).parent / "data" / "products.json"))
INGEST_COOLDOWN = int(os.environ.get("INGEST_COOLDOWN_SECONDS", "30"))  # espera mínima entre ingestas de un producto
SEARCH_RATE_LIMIT = int(os.environ.get("SEARCH_RATE_LIMIT_PER_MINUTE", "20"))
DEFAULT_SOURCE = os.environ.get("INGEST_SOURCE", "wikipedia")
if DEFAULT_SOURCE not in ("wikipedia", "simulated"):
    raise RuntimeError("INGEST_SOURCE must be 'wikipedia' or 'simulated'")

# ======================================================================
# 2. Aplicación y documentación OpenAPI (visible en /docs y /openapi.json)
# ======================================================================
DESCRIPTION = """
Servicio que vigila productos y nichos de mercado, **ingiere su interés diario desde una API externa**
(Wikimedia Pageviews) y detecta cuándo se dispara respecto a su media reciente.

### Autenticación y autorización
Se envía la clave en la cabecera `X-API-Key` (botón **Authorize**). Hay tres niveles:

| Nivel | Qué puede hacer | Cómo |
|---|---|---|
| Público | Leer productos, series, picos y rankings; buscar términos | Sin clave |
| `ingest` | Lo público + ejecutar la ingesta | `INGEST_API_KEY` |
| `admin` | Todo: crear/borrar productos, ingesta, resumen y registro | `ADMIN_API_KEY` |

Sin clave o con clave inválida → **401**. Clave válida pero sin permiso para esa operación → **403**.

### Errores
Todos los errores tienen la forma `{"detail": "..."}`: 401, 403, 404, 409 (duplicado o sin histórico),
422 (datos inválidos), 429 (demasiadas peticiones), 502 (la API externa falla) y 503 (fuente no disponible).
"""
TAGS = [
    {"name": "Sistema", "description": "Estado del servicio."},
    {"name": "Productos", "description": "Catálogo de productos y nichos vigilados."},
    {"name": "Análisis", "description": "Series de interés, detección de picos y ranking."},
    {"name": "Búsqueda", "description": "Interés mensual de cualquier término con fuentes gratuitas."},
    {"name": "Ingesta", "description": "Carga de datos desde la API externa, con validación y reglas."},
    {"name": "Administración", "description": "Operaciones restringidas al administrador."},
]
app = FastAPI(
    title="TrendWatch API",
    version="0.3.0",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    contact={"name": "Equipo TrendWatch", "url": "https://github.com/Proyectos-UE/Proyecto_Infraestructuras_6_7"},
)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Último recurso: nunca se devuelve la traza al cliente, solo se registra en el log."""
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ======================================================================
# 3. Modelos Pydantic
# ======================================================================
class ErrorResponse(BaseModel):
    detail: str


class SeriesPoint(BaseModel):
    """Interés de un producto en un día."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    value: float = Field(ge=0)


class ProductDraft(BaseModel):
    """Producto enviado por el cliente."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={"examples": [{"name": "Calcetines de navidad", "category": "ocio"}]},
    )

    name: str = Field(min_length=1, max_length=80, description="Nombre del producto o nicho.")
    category: str = Field(min_length=1, max_length=40, description="Categoría en minúsculas, p. ej. 'hogar'.")
    wiki_article: str | None = Field(
        default=None, min_length=1, max_length=120,
        description="Título exacto del artículo de Wikipedia si no coincide con el nombre.",
    )
    source: str = Field(default="manual", min_length=1, max_length=30, description="Origen de los datos.")
    series: list[SeriesPoint] = Field(default_factory=list, max_length=730)

    @model_validator(mode="after")
    def check_and_sort_series(self):
        """Rechaza fechas repetidas y deja la serie ordenada por fecha."""
        dates = [point.date for point in self.series]
        if len(set(dates)) != len(dates):
            raise ValueError("Duplicate dates in series")
        self.series.sort(key=lambda point: point.date)
        return self


class Product(ProductDraft):
    id: int = Field(gt=0)


class ProductRead(BaseModel):
    id: int
    name: str
    category: str
    wiki_article: str | None
    source: str
    points: int


class ProductPage(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int


class SeriesRead(BaseModel):
    id: int
    name: str
    series: list[SeriesPoint]


class SpikeRead(BaseModel):
    id: int
    name: str
    is_spike: bool
    z_score: float
    growth: float
    last_value: float
    baseline_mean: float


class RisingItem(BaseModel):
    id: int
    name: str
    category: str
    growth: float
    z_score: float
    is_spike: bool


class MonthPoint(BaseModel):
    month: str
    value: float
    partial: bool = Field(description="True si es el mes en curso (aún incompleto).")


class SearchRead(BaseModel):
    query: str
    source: str
    unit: str = Field(description="Qué significa el número (no son búsquedas exactas).")
    geo: str | None
    note: str | None
    months: list[MonthPoint]


class IngestReport(BaseModel):
    """Resultado de la ingesta de un producto."""

    product_id: int
    name: str
    source: str
    status: Literal["ok", "no_data"]
    window_start: dt.date
    window_end: dt.date
    received: int = Field(description="Registros recibidos de la API externa.")
    accepted: int = Field(description="Registros que pasaron la validación y las reglas.")
    rejected: int
    inserted: int = Field(description="Días nuevos añadidos a la serie.")
    updated: int = Field(description="Días existentes cuyo valor cambió.")
    replaced_previous_source: bool = Field(description="True si la serie anterior era de otra fuente y se sustituyó.")
    rejected_samples: list[str]
    total_points: int


class IngestError(BaseModel):
    product_id: int
    name: str
    status_code: int
    detail: str


class IngestBatch(BaseModel):
    requested: int
    succeeded: int
    failed: int
    reports: list[IngestReport]
    errors: list[IngestError]


class IngestRun(BaseModel):
    at: dt.datetime
    product_id: int
    name: str
    source: str
    status: str
    detail: str


def to_read(product: Product) -> ProductRead:
    return ProductRead(
        id=product.id, name=product.name, category=product.category,
        wiki_article=product.wiki_article, source=product.source, points=len(product.series),
    )


# ======================================================================
# 4. Datos: carga validada al arrancar y guardado atómico
# ======================================================================
LOCK = threading.RLock()  # los endpoints se ejecutan en hilos distintos

CATALOG: list[Product] = TypeAdapter(list[Product]).validate_json(DATA_FILE.read_text(encoding="utf-8"))
if len({row.id for row in CATALOG}) != len(CATALOG):
    raise ValueError("Duplicate product identifiers")
if len({row.name.lower() for row in CATALOG}) != len(CATALOG):
    raise ValueError("Duplicate product names")

# Un ID borrado no se vuelve a asignar mientras el servicio esté en marcha
NEXT_ID = max((row.id for row in CATALOG), default=0) + 1
RUNS: deque[IngestRun] = deque(maxlen=200)  # registro de las últimas ingestas
_last_ingest: dict[int, float] = {}
_search_hits: dict[str, deque] = defaultdict(deque)


def save_catalog() -> None:
    """Escribe el catálogo en disco de forma atómica (archivo temporal + reemplazo)."""
    payload = json.dumps([row.model_dump(mode="json") for row in CATALOG], ensure_ascii=False, indent=1)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, DATA_FILE)


def find_or_404(product_id: int) -> Product:
    product = next((row for row in CATALOG if row.id == product_id), None)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


# ======================================================================
# 5. Autenticación (¿quién eres?) y autorización (¿puedes hacer esto?)
# ======================================================================
key_header = APIKeyHeader(
    name="X-API-Key", auto_error=False, scheme_name="ApiKeyAuth",
    description="Clave de API. Se define en ADMIN_API_KEY o INGEST_API_KEY (ver README).",
)


def _role_of(key: str | None) -> str | None:
    """Devuelve 'admin', 'ingest' o None. Comparación en tiempo constante."""
    if key is None:
        return None
    candidate = key.encode()
    if secrets.compare_digest(candidate, ADMIN_API_KEY.encode()):
        return "admin"
    if INGEST_API_KEY and secrets.compare_digest(candidate, INGEST_API_KEY.encode()):
        return "ingest"
    return None


def require_roles(*allowed: str):
    def dependency(key: str | None = Security(key_header)) -> str:
        role = _role_of(key)
        if role is None:
            raise HTTPException(401, "Invalid credentials", headers={"WWW-Authenticate": "APIKey"})
        if role not in allowed:
            raise HTTPException(403, "This key has no permission for this operation")
        return role

    return dependency


require_admin = require_roles("admin")
require_ingest = require_roles("admin", "ingest")

R401 = {401: {"model": ErrorResponse, "description": "Missing or invalid API key"}}
R403 = {403: {"model": ErrorResponse, "description": "Valid key without permission for this operation"}}
R404 = {404: {"model": ErrorResponse, "description": "Product not found"}}


def limit_search(request: Request) -> None:
    """Límite de peticiones por IP: /v1/search reenvía a servicios externos y no debe poder abusarse."""
    queue = _search_hits[request.client.host if request.client else "unknown"]
    now = time.monotonic()
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= SEARCH_RATE_LIMIT:
        raise HTTPException(429, "Too many searches, wait a minute", headers={"Retry-After": "60"})
    queue.append(now)


# ======================================================================
# 6. Endpoints públicos
# ======================================================================
@app.get("/health", tags=["Sistema"], summary="Estado del servicio")
def health() -> dict[str, str]:
    """Report process health."""
    return {"status": "ok"}


@app.get("/v1/products", tags=["Productos"], summary="Listar productos")
def list_products(
    category: Annotated[str | None, Query(max_length=40, description="Categoría exacta (distingue mayúsculas), p. ej. 'hogar'.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductPage:
    """Página de productos vigilados, filtrada por categoría y ordenada por id."""
    rows = sorted((row for row in CATALOG if category is None or row.category == category), key=lambda row: row.id)
    return ProductPage(items=[to_read(row) for row in rows[offset: offset + limit]], total=len(rows), limit=limit, offset=offset)


@app.get("/v1/products/{product_id}", tags=["Productos"], summary="Detalle de un producto",
         response_model=ProductRead, responses=R404)
def get_product(product_id: int) -> ProductRead:
    return to_read(find_or_404(product_id))


@app.get("/v1/products/{product_id}/series", tags=["Análisis"], summary="Serie diaria de interés", responses=R404)
def get_series(product_id: int, days: Annotated[int, Query(ge=1, le=730)] = 90) -> SeriesRead:
    product = find_or_404(product_id)
    return SeriesRead(id=product.id, name=product.name, series=product.series[-days:])


@app.get("/v1/products/{product_id}/spike", tags=["Análisis"], summary="¿Hay un pico ahora?",
         responses={**R404, 409: {"model": ErrorResponse, "description": "Not enough history to analyze"}})
def get_spike(
    product_id: int,
    window: Annotated[int, Query(ge=7, le=180, description="Días anteriores que forman la media de referencia.")] = 28,
    z_threshold: Annotated[float, Query(gt=0, description="Desviaciones sobre la media a partir de las cuales hay pico.")] = 3.0,
) -> SpikeRead:
    """Compara el último dato con la media de los `window` días anteriores (z-score y crecimiento)."""
    product = find_or_404(product_id)
    result = analyze([p.value for p in product.series], window=window, z_threshold=z_threshold)
    if result is None:
        raise HTTPException(409, "Not enough history to analyze")
    return SpikeRead(id=product.id, name=product.name, **result)


@app.get("/v1/rankings/rising", tags=["Análisis"], summary="Ranking de productos en ascenso")
def rising(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[RisingItem]:
    ranking = []
    for row in CATALOG:
        result = analyze([p.value for p in row.series])
        if result is not None:
            ranking.append(RisingItem(id=row.id, name=row.name, category=row.category,
                                      growth=result["growth"], z_score=result["z_score"], is_spike=result["is_spike"]))
    return sorted(ranking, key=lambda item: item.growth, reverse=True)[:limit]


@app.get("/v1/search", tags=["Búsqueda"], summary="Interés mensual de cualquier término",
         dependencies=[Depends(limit_search)],
         responses={
             404: {"model": ErrorResponse, "description": "No source has data for that term"},
             429: {"model": ErrorResponse, "description": "Too many searches"},
             503: {"model": ErrorResponse, "description": "Sources not responding (e.g. Google blocked the request)"},
         })
def search_term(
    q: Annotated[str, Query(max_length=80, description="Término a buscar, p. ej. 'calcetines de navidad'.")],
    months: Annotated[int, Query(ge=1, le=240)] = 12,
    source: Annotated[Literal["auto", "trends", "wikipedia"], Query()] = "auto",
    geo: Annotated[str, Query(pattern="^([A-Za-z]{2})?$", description="País (ES, MX…); vacío = mundo.")] = "ES",
) -> SearchRead:
    """Interés mensual con fuentes gratuitas. El valor de Google Trends es un índice relativo de 0 a 100, no un número de búsquedas."""
    term = q.strip()
    if len(term) < 2:
        raise HTTPException(422, "The query must have at least 2 characters")
    try:
        return SearchRead(**search.get_monthly(term, months, geo.upper(), source))
    except search.NoData as exc:
        raise HTTPException(404, str(exc))
    except search.SourceUnavailable as exc:
        raise HTTPException(503, str(exc))


# ======================================================================
# 7. Ingesta (API externa -> validación -> reglas -> carga -> informe)
# ======================================================================
def _record(product: Product, source: str, status: str, detail: str) -> None:
    RUNS.append(IngestRun(at=dt.datetime.now(dt.timezone.utc), product_id=product.id, name=product.name,
                          source=source, status=status, detail=detail))
    log.info("ingest product=%s source=%s status=%s %s", product.id, source, status, detail)


def run_ingest(product: Product, days: int, source: str) -> IngestReport:
    """Ingesta de UN producto. Lanza HTTPException con el código HTTP adecuado si algo falla."""
    try:
        user_agent = os.environ.get("WIKI_USER_AGENT")
        if source == "wikipedia" and not user_agent:
            raise HTTPException(503, "Ingestion not configured: define WIKI_USER_AGENT (ver .env.example)")

        wait = INGEST_COOLDOWN - (time.monotonic() - _last_ingest.get(product.id, float("-inf")))
        if wait > 0:
            raise HTTPException(429, f"Product ingested recently, wait {int(wait) + 1} s",
                                headers={"Retry-After": str(int(wait) + 1)})

        start, end = ingest.window(days)
        _last_ingest[product.id] = time.monotonic()  # también si falla: no se martillea a la API externa
        try:
            result = ingest.get_points(source, product.wiki_article or product.name, start, end, user_agent)
        except ingest.UpstreamError as exc:
            raise HTTPException(502, f"External API error: {exc}")
        except ingest.QualityError as exc:
            raise HTTPException(422, f"Data rejected, nothing was loaded: {exc}")

        with LOCK:
            replaced = bool(result.points) and bool(product.series) and product.source != source
            existing = {} if replaced else {point.date: point for point in product.series}
            inserted = updated = 0
            for day, value in result.points.items():
                if day not in existing:
                    inserted += 1
                elif existing[day].value != value:
                    updated += 1
                existing[day] = SeriesPoint(date=day, value=value)
            if result.points:
                product.series = sorted(existing.values(), key=lambda point: point.date)[-730:]
                product.source = source
                save_catalog()
            report = IngestReport(
                product_id=product.id, name=product.name, source=source,
                status="ok" if result.points else "no_data", window_start=start, window_end=end,
                received=result.received, accepted=len(result.points), rejected=result.rejected,
                inserted=inserted, updated=updated, replaced_previous_source=replaced,
                rejected_samples=result.samples, total_points=len(product.series),
            )
        _record(product, source, report.status,
                f"received={report.received} accepted={report.accepted} rejected={report.rejected} inserted={inserted} updated={updated}")
        return report
    except HTTPException as exc:
        _record(product, source, "failed", f"{exc.status_code} {exc.detail}")
        raise


IngestSource = Annotated[Literal["wikipedia", "simulated"], Query(description="'wikipedia' = API real de Wikimedia; 'simulated' = API simulada (sin Internet).")]
IngestDays = Annotated[int, Query(ge=7, le=365, description="Días de histórico a pedir (hasta ayer).")]
INGEST_ERRORS = {
    **R401, **R403,
    422: {"model": ErrorResponse, "description": "Invalid parameters or data rejected by the quality rules (nothing loaded)"},
    429: {"model": ErrorResponse, "description": "Product ingested too recently"},
    502: {"model": ErrorResponse, "description": "The external API failed"},
    503: {"model": ErrorResponse, "description": "Ingestion not configured (WIKI_USER_AGENT missing)"},
}


@app.post("/v1/products/{product_id}/ingest", tags=["Ingesta"], summary="Ingerir datos de un producto",
          dependencies=[Depends(require_ingest)], responses={**INGEST_ERRORS, **R404})
def ingest_product(product_id: int, days: IngestDays = 90, source: IngestSource = DEFAULT_SOURCE) -> IngestReport:
    """Pide el histórico a la API externa, lo valida registro a registro, aplica las reglas y lo fusiona de forma
    idempotente (repetir la ingesta no duplica datos). Si cambia la fuente, la serie anterior se sustituye."""
    return run_ingest(find_or_404(product_id), days, source)


@app.post("/v1/ingest", tags=["Ingesta"], summary="Ingerir datos de todos los productos",
          dependencies=[Depends(require_ingest)], responses=INGEST_ERRORS)
def ingest_all(
    days: IngestDays = 90,
    source: IngestSource = DEFAULT_SOURCE,
    category: Annotated[str | None, Query(max_length=40)] = None,
) -> IngestBatch:
    """Ingesta por lotes. Un fallo en un producto no detiene el resto: se informa en `errors`."""
    targets = [row for row in CATALOG if category is None or row.category == category]
    reports, errors = [], []
    for product in targets:
        try:
            reports.append(run_ingest(product, days, source))
        except HTTPException as exc:
            errors.append(IngestError(product_id=product.id, name=product.name, status_code=exc.status_code, detail=str(exc.detail)))
    return IngestBatch(requested=len(targets), succeeded=len(reports), failed=len(errors), reports=reports, errors=errors)


# ======================================================================
# 8. Endpoints de administración
# ======================================================================
@app.post("/v1/products", tags=["Productos"], summary="Añadir un producto", status_code=201,
          response_model=ProductRead, dependencies=[Depends(require_admin)],
          responses={**R401, **R403, 409: {"model": ErrorResponse, "description": "Product name already exists"}})
def create_product(body: ProductDraft, response: Response) -> ProductRead:
    global NEXT_ID
    with LOCK:
        if any(row.name.lower() == body.name.lower() for row in CATALOG):
            raise HTTPException(409, "Product name already exists")
        product = Product(id=NEXT_ID, **body.model_dump())
        NEXT_ID += 1
        CATALOG.append(product)
        save_catalog()
    response.headers["Location"] = f"/v1/products/{product.id}"
    return to_read(product)


@app.delete("/v1/products/{product_id}", tags=["Productos"], summary="Borrar un producto", status_code=204,
            dependencies=[Depends(require_admin)], responses={**R401, **R403, **R404})
def delete_product(product_id: int) -> Response:
    with LOCK:
        CATALOG.remove(find_or_404(product_id))
        save_catalog()
    return Response(status_code=204)


@app.get("/v1/admin/summary", tags=["Administración"], summary="Resumen operativo",
         dependencies=[Depends(require_admin)], responses={**R401, **R403})
def admin_summary() -> dict[str, int]:
    return {"products_loaded": len(CATALOG), "points_loaded": sum(len(row.series) for row in CATALOG)}


@app.get("/v1/admin/ingestions", tags=["Administración"], summary="Registro de las últimas ingestas",
         dependencies=[Depends(require_admin)], responses={**R401, **R403})
def list_ingestions(limit: Annotated[int, Query(ge=1, le=200)] = 20) -> list[IngestRun]:
    """Las ingestas más recientes primero (correctas, sin datos y fallidas)."""
    return list(reversed(RUNS))[:limit]
