import datetime as dt
import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from spike import analyze

# 1. Inicialización de la aplicación
app = FastAPI(title="TrendWatch API", version="0.1.0")

# 2. Configuración y secretos
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
if not ADMIN_API_KEY:
    raise RuntimeError("ADMIN_API_KEY is required")


# 3. Modelos Pydantic
class SeriesPoint(BaseModel):
    """Interés de un producto en un día."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date
    value: float = Field(ge=0)


class ProductDraft(BaseModel):
    """Describe a product submitted by the client."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    source: str = Field(default="manual", min_length=1, max_length=30)
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
    """Producto guardado, con identificador."""

    id: int = Field(gt=0)


class ProductRead(BaseModel):
    """Describe a public product (sin la serie, que va en su propio endpoint)."""

    id: int
    name: str
    category: str
    source: str
    points: int


class ProductPage(BaseModel):
    """Describe one page of products."""

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


def to_read(product: Product) -> ProductRead:
    return ProductRead(
        id=product.id,
        name=product.name,
        category=product.category,
        source=product.source,
        points=len(product.series),
    )


# 4. Carga y validación de datos (si el archivo no sirve, el arranque falla)
DATA_FILE = Path(__file__).parent / "data" / "products.json"

CATALOG: list[Product] = TypeAdapter(list[Product]).validate_json(
    DATA_FILE.read_text(encoding="utf-8")
)

if len({row.id for row in CATALOG}) != len(CATALOG):
    raise ValueError("Duplicate product identifiers")
if len({row.name.lower() for row in CATALOG}) != len(CATALOG):
    raise ValueError("Duplicate product names")

# Contador propio: un ID borrado no se vuelve a asignar a otro producto
NEXT_ID = max((row.id for row in CATALOG), default=0) + 1


def find_or_404(product_id: int) -> Product:
    product = next((row for row in CATALOG if row.id == product_id), None)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


# 5. Control de acceso por API key
key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_key(key: str | None = Security(key_header)) -> None:
    """Reject absent or invalid administrative credentials."""
    if key is None or not secrets.compare_digest(
        key.encode(), ADMIN_API_KEY.encode()
    ):
        raise HTTPException(
            401,
            "Invalid credentials",
            headers={"WWW-Authenticate": "APIKey"},
        )


# 6. Endpoints públicos
@app.get("/health")
def health() -> dict[str, str]:
    """Report process health."""
    return {"status": "ok"}


@app.get("/v1/products")
def list_products(
    category: Annotated[
        str | None,
        Query(
            max_length=40,
            description="Exact category match (case-sensitive), e.g. 'hogar'.",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductPage:
    """Read a bounded page of watched products, filtered and ordered by id."""
    rows = [row for row in CATALOG if category is None or row.category == category]
    rows.sort(key=lambda row: row.id)
    return ProductPage(
        items=[to_read(row) for row in rows[offset : offset + limit]],
        total=len(rows),
        limit=limit,
        offset=offset,
    )


@app.get(
    "/v1/products/{product_id}",
    response_model=ProductRead,
    responses={404: {"description": "Product not found"}},
)
def get_product(product_id: int) -> ProductRead:
    """Return a validated public representation."""
    return to_read(find_or_404(product_id))


@app.get(
    "/v1/products/{product_id}/series",
    responses={404: {"description": "Product not found"}},
)
def get_series(
    product_id: int,
    days: Annotated[int, Query(ge=1, le=730)] = 90,
) -> SeriesRead:
    """Return the last `days` points of the interest series."""
    product = find_or_404(product_id)
    return SeriesRead(id=product.id, name=product.name, series=product.series[-days:])


@app.get(
    "/v1/products/{product_id}/spike",
    responses={
        404: {"description": "Product not found"},
        409: {"description": "Not enough history to analyze"},
    },
)
def get_spike(
    product_id: int,
    window: Annotated[int, Query(ge=7, le=180)] = 28,
    z_threshold: Annotated[float, Query(gt=0)] = 3.0,
) -> SpikeRead:
    """Tell whether the latest data point is a spike against its recent baseline."""
    product = find_or_404(product_id)
    result = analyze(
        [point.value for point in product.series],
        window=window,
        z_threshold=z_threshold,
    )
    if result is None:
        raise HTTPException(409, "Not enough history to analyze")
    return SpikeRead(id=product.id, name=product.name, **result)


@app.get("/v1/rankings/rising")
def rising(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> list[RisingItem]:
    """Products ordered by growth against their recent baseline."""
    ranking = []
    for row in CATALOG:
        result = analyze([point.value for point in row.series])
        if result is not None:
            ranking.append(
                RisingItem(
                    id=row.id,
                    name=row.name,
                    category=row.category,
                    growth=result["growth"],
                    z_score=result["z_score"],
                    is_spike=result["is_spike"],
                )
            )
    ranking.sort(key=lambda item: item.growth, reverse=True)
    return ranking[:limit]


# 7. Endpoints protegidos (requieren la cabecera X-API-Key)
@app.post(
    "/v1/products",
    status_code=201,
    response_model=ProductRead,
    dependencies=[Depends(require_key)],
    responses={
        401: {"description": "Missing or invalid API key"},
        409: {"description": "Product name already exists"},
    },
)
def create_product(body: ProductDraft, response: Response) -> ProductRead:
    """Add a product to the watchlist."""
    global NEXT_ID
    if any(row.name.lower() == body.name.lower() for row in CATALOG):
        raise HTTPException(409, "Product name already exists")
    product = Product(id=NEXT_ID, **body.model_dump())
    NEXT_ID += 1
    CATALOG.append(product)
    response.headers["Location"] = f"/v1/products/{product.id}"
    return to_read(product)


@app.delete(
    "/v1/products/{product_id}",
    status_code=204,
    dependencies=[Depends(require_key)],
    responses={
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Product not found"},
    },
)
def delete_product(product_id: int) -> Response:
    """Delete a product from the watchlist."""
    for index, product in enumerate(CATALOG):
        if product.id == product_id:
            CATALOG.pop(index)
            return Response(status_code=204)

    raise HTTPException(status_code=404, detail="Product not found")


@app.get(
    "/v1/admin/summary",
    dependencies=[Depends(require_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)
def admin_summary() -> dict[str, int]:
    """Return a protected operational summary."""
    return {
        "products_loaded": len(CATALOG),
        "points_loaded": sum(len(row.series) for row in CATALOG),
    }
