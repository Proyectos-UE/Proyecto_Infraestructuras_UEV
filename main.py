import os
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# 1. Inicialización de la aplicación
app = FastAPI(title="Catalog API", version="0.1.0")

# 2. Configuración y secretos
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
if not ADMIN_API_KEY:
    raise RuntimeError("ADMIN_API_KEY is required")


# 3. Modelos Pydantic
class RecordDraft(BaseModel):
    """Describe a record submitted by the client."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)


class RecordRead(RecordDraft):
    """Describe a public catalog record."""

    id: int = Field(gt=0)


class RecordPage(BaseModel):
    """Describe one page of catalog records."""

    items: list[RecordRead]
    total: int
    limit: int
    offset: int


# 4. Carga y validación de datos (si el archivo no sirve, el arranque falla)
DATA_FILE = Path(__file__).parent / "data" / "records.json"

CATALOG: list[RecordRead] = TypeAdapter(list[RecordRead]).validate_json(
    DATA_FILE.read_text(encoding="utf-8")
)

if len({row.id for row in CATALOG}) != len(CATALOG):
    raise ValueError("Duplicate record identifiers")

# Contador propio: un ID borrado no se vuelve a asignar a otro registro
NEXT_ID = max((row.id for row in CATALOG), default=0) + 1


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


@app.get("/v1/records")
def list_records(
    category: Annotated[
        str | None,
        Query(
            max_length=40,
            description="Exact category match (case-sensitive), e.g. 'music'.",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordPage:
    """Read a bounded page of catalog records, filtered and ordered by id."""
    rows = [row for row in CATALOG if category is None or row.category == category]
    rows.sort(key=lambda row: row.id)
    return RecordPage(
        items=rows[offset : offset + limit],
        total=len(rows),
        limit=limit,
        offset=offset,
    )


@app.get(
    "/v1/records/{record_id}",
    response_model=RecordRead,
    responses={404: {"description": "Record not found"}},
)
def get_record(record_id: int) -> RecordRead:
    """Return a validated public representation."""
    record = next((row for row in CATALOG if row.id == record_id), None)
    if record is None:
        raise HTTPException(404, "Record not found")
    return record


# 7. Endpoints protegidos (requieren la cabecera X-API-Key)
@app.post(
    "/v1/records",
    status_code=201,
    response_model=RecordRead,
    dependencies=[Depends(require_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)
def create_record(body: RecordDraft, response: Response) -> RecordRead:
    """Create a record in the teaching-only catalog."""
    global NEXT_ID
    record = RecordRead(id=NEXT_ID, **body.model_dump())
    NEXT_ID += 1
    CATALOG.append(record)
    response.headers["Location"] = f"/v1/records/{record.id}"
    return record


@app.delete(
    "/v1/records/{record_id}",
    status_code=204,
    dependencies=[Depends(require_key)],
    responses={
        401: {"description": "Missing or invalid API key"},
        404: {"description": "Record not found"},
    },
)
def delete_record(record_id: int) -> Response:
    """Delete a record from the teaching catalog."""
    for index, record in enumerate(CATALOG):
        if record.id == record_id:
            CATALOG.pop(index)
            return Response(status_code=204)

    raise HTTPException(status_code=404, detail="Record not found")


@app.get(
    "/v1/admin/summary",
    dependencies=[Depends(require_key)],
    responses={401: {"description": "Missing or invalid API key"}},
)
def admin_summary() -> dict[str, int]:
    """Return a protected operational summary."""
    return {"records_loaded": len(CATALOG)}