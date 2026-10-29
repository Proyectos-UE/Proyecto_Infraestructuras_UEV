# TrendWatch API

Detección temprana de picos de interés en productos y nichos de mercado.
Proyecto de **Infraestructuras y Computación en la Nube** (Grado en Ciencia de Datos) · segundo entregable.

**Equipo:** Pablo Díaz · Eduardo Caicedo · Jordi Aguado · Alessandro Matos

## Qué hace

Una API REST (FastAPI) que vigila una lista de productos, **ingiere su interés diario desde una API externa**
(Wikimedia Pageviews, real o simulada), valida los datos, y detecta cuándo el interés de un producto se dispara
respecto a su media reciente. Mide **interés** (visitas), no ventas ni número exacto de búsquedas.

## Puesta en marcha

Requisitos: **Python 3.10 o superior**.

```powershell
# Windows (PowerShell)
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
copy .env.example .env            # y edita .env: pon tus claves y tu contacto en WIKI_USER_AGENT
python -m uvicorn main:app --reload
```

```bash
# Linux / macOS
python3 -m venv venv && source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env              # y edita .env
python -m uvicorn main:app --reload
```

- Documentación interactiva (Swagger): http://127.0.0.1:8000/docs · Especificación OpenAPI: http://127.0.0.1:8000/openapi.json
- En `/docs`, el botón **Authorize** permite pegar la clave para probar los endpoints protegidos.
- Si PowerShell no deja activar el entorno: `Set-ExecutionPolicy -Scope Process Bypass`.

### Configuración (variables de entorno o `.env`)

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `ADMIN_API_KEY` | **Sí** (la API no arranca sin ella) | Clave de administrador |
| `INGEST_API_KEY` | No | Clave que solo permite ingerir (mínimo privilegio). Debe ser distinta de la anterior |
| `WIKI_USER_AGENT` | Solo para la ingesta real | Wikimedia exige identificarse con un contacto |
| `INGEST_SOURCE` | No (`wikipedia`) | Fuente por defecto de la ingesta: `wikipedia` o `simulated` |
| `INGEST_COOLDOWN_SECONDS` | No (`30`) | Espera mínima entre ingestas del mismo producto |
| `SEARCH_RATE_LIMIT_PER_MINUTE` | No (`20`) | Límite de búsquedas por minuto y por IP |
| `DATA_FILE` | No | Archivo de datos (por defecto `data/products.json`) |

Los secretos **nunca** van en el código: se leen del entorno o de `.env`, que está en `.gitignore`.
`.env.example` solo contiene valores de ejemplo.

## Autenticación y autorización

La clave se envía en la cabecera `X-API-Key`.

| Nivel | Puede hacer | Clave |
|---|---|---|
| Público | Leer productos, series, picos, rankings y buscar | Ninguna |
| `ingest` | Lo público + ejecutar la ingesta | `INGEST_API_KEY` |
| `admin` | Todo: crear/borrar productos, ingesta, resumen y registro de ingestas | `ADMIN_API_KEY` |

Sin clave o con una inválida → **401**. Clave válida pero sin permiso para esa operación → **403**.
La comparación de claves es en tiempo constante. La clave de `ingest` está pensada para el proceso automático
que actualiza los datos: si se filtrara, no permitiría borrar ni crear nada.

## Endpoints

| Método y ruta | Qué hace | Acceso |
|---|---|---|
| `GET /health` | Estado del servicio | Público |
| `GET /v1/products` | Lista productos (`category`, `limit`, `offset`) | Público |
| `GET /v1/products/{id}` | Detalle de un producto | Público |
| `GET /v1/products/{id}/series` | Serie diaria de interés (`days`) | Público |
| `GET /v1/products/{id}/spike` | ¿Hay un pico ahora? (`window`, `z_threshold`) | Público |
| `GET /v1/rankings/rising` | Productos ordenados por crecimiento | Público |
| `GET /v1/search?q=…` | Interés mensual de cualquier término | Público (límite por IP) |
| `POST /v1/products/{id}/ingest` | Ingesta de un producto | ingest / admin |
| `POST /v1/ingest` | Ingesta de todos los productos (o de una `category`) | ingest / admin |
| `POST /v1/products` | Añadir un producto | admin |
| `DELETE /v1/products/{id}` | Borrar un producto | admin |
| `GET /v1/admin/summary` | Resumen operativo | admin |
| `GET /v1/admin/ingestions` | Registro de las últimas ingestas | admin |

## Ejemplos de peticiones

### PowerShell

```powershell
$base  = "http://127.0.0.1:8000"
$admin = @{ "X-API-Key" = "TU_ADMIN_API_KEY" }

# Lectura pública
Invoke-RestMethod "$base/v1/products?category=movilidad&limit=5"
Invoke-RestMethod "$base/v1/products/1/spike"
Invoke-RestMethod "$base/v1/rankings/rising?limit=5"

# Crear un producto (admin)  -> 201
Invoke-RestMethod -Method Post "$base/v1/products" -Headers $admin -ContentType "application/json" `
  -Body '{"name":"Calcetines de navidad","category":"ocio"}'

# Sin clave -> 401 (para ver el código de estado)
try { Invoke-RestMethod -Method Post "$base/v1/products" -ContentType "application/json" `
        -Body '{"name":"X","category":"y"}' } catch { $_.Exception.Response.StatusCode.value__ }

# Datos inválidos (nombre vacío) -> 422
try { Invoke-RestMethod -Method Post "$base/v1/products" -Headers $admin -ContentType "application/json" `
        -Body '{"name":"","category":"y"}' } catch { $_.Exception.Response.StatusCode.value__ }

# Búsqueda libre
Invoke-RestMethod "$base/v1/search?q=calcetines de navidad&months=24"
```

### curl (Linux / macOS)

```bash
curl "http://127.0.0.1:8000/v1/products?limit=2"
curl -i -X POST http://127.0.0.1:8000/v1/products -H "Content-Type: application/json" \
     -d '{"name":"X","category":"y"}'                                   # 401
curl -X POST http://127.0.0.1:8000/v1/products -H "X-API-Key: $ADMIN_API_KEY" \
     -H "Content-Type: application/json" -d '{"name":"Mi producto","category":"ocio"}'   # 201
```

## Proceso de ingesta (reproducible)

La ingesta trae el histórico de visitas de un artículo desde una **API externa** y lo incorpora a la serie del
producto. Hay dos fuentes con **la misma tubería de validación**:

- `wikipedia`: API real de Wikimedia Pageviews (necesita Internet y `WIKI_USER_AGENT`).
- `simulated`: API simulada con el mismo formato de respuesta (no necesita Internet; datos deterministas).

### Reproducirla paso a paso

Con la API arrancada y `ADMIN_API_KEY` o `INGEST_API_KEY` en `$h`:

```powershell
$h = @{ "X-API-Key" = "TU_ADMIN_API_KEY" }      # también vale la INGEST_API_KEY

# 1) Sin Internet: ingesta SIMULADA de todos los productos (60 días)
Invoke-RestMethod -Method Post "$base/v1/ingest?source=simulated&days=60" -Headers $h

# 2) Comprobar el resultado: ranking de productos en ascenso (Freidora de aire y Pickleball terminan con pico)
Invoke-RestMethod "$base/v1/rankings/rising?limit=5"

# 3) Ingesta REAL de un producto (requiere WIKI_USER_AGENT en .env y Internet)
# La ingesta simulada del paso 1 incluyó este producto; esperar 30 s (o el valor configurado).
Start-Sleep -Seconds 30
Invoke-RestMethod -Method Post "$base/v1/products/1/ingest?source=wikipedia&days=90" -Headers $h

# 4) Repetirla tras otra espera NO duplica datos: inserted=0, updated=0
Start-Sleep -Seconds 30
Invoke-RestMethod -Method Post "$base/v1/products/1/ingest?source=wikipedia&days=90" -Headers $h

# 5) Registro de las ingestas (solo admin)
Invoke-RestMethod "$base/v1/admin/ingestions?limit=10" -Headers @{ "X-API-Key" = "TU_ADMIN_API_KEY" }
```

Nota: entre dos ingestas del mismo producto hay una espera mínima (`INGEST_COOLDOWN_SECONDS`); si no se respeta, la API
responde 429 con la cabecera `Retry-After`. Si un artículo de Wikipedia no se llama igual que el producto, se
indica el título exacto en el campo `wiki_article` al crearlo.

### Etapas y reglas

| Etapa | Qué hace | Si falla |
|---|---|---|
| 1. Extracción | Pide los datos a la API externa (timeout 15 s, un reintento ante fallos de red o 5xx) | **502** |
| 2. Validación | Cada registro se valida con Pydantic: fecha `AAAAMMDDHH` válida y visitas enteras ≥ 0. Un registro malo se rechaza sin afectar al resto | Se descarta y se cuenta |
| 3. Reglas | Solo fechas dentro de la ventana (los `days` días hasta **ayer**); sin fechas repetidas; **calidad mínima**: si más del 20 % de los registros son inválidos se rechaza la tanda entera | **422**, no se carga nada |
| 4. Carga | Fusión por fecha (**idempotente**). Si cambia la fuente, la serie anterior se **sustituye** (una serie nunca mezcla orígenes). Guardado atómico en `data/products.json` | — |

Si la API externa no tiene datos de ese artículo (404 de Wikimedia), el informe indica `status: "no_data"` y los
datos existentes no se tocan.

### Informe de cada ingesta

```json
{
  "product_id": 1, "name": "Freidora de aire", "source": "simulated", "status": "ok",
  "window_start": "2026-08-30", "window_end": "2026-10-28",
  "received": 60, "accepted": 60, "rejected": 0,
  "inserted": 60, "updated": 0, "replaced_previous_source": true,
  "rejected_samples": [], "total_points": 60
}
```

### Ingesta automática diaria

El proceso periódico debe usar la **clave de ingesta** (permisos mínimos). Ejemplo con cron (Linux/macOS):

```bash
0 6 * * *  curl -s -X POST "http://127.0.0.1:8000/v1/ingest?source=wikipedia&days=7" -H "X-API-Key: $INGEST_API_KEY"
```

En Windows se puede programar el mismo `Invoke-RestMethod` con el Programador de tareas.

### Cómo se verifica la validación sin Internet

`test_ingest.py` simula la API externa con respuestas falsas: registros con visitas negativas, fechas imposibles,
fuera de ventana o repetidas; respuestas que no son JSON; errores 429/5xx; caídas de red; y datos de mala calidad
(se comprueba que no se carga nada).

## Errores controlados

Todos los errores tienen la forma `{"detail": "..."}` y están documentados en `/docs`.

| Código | Cuándo |
|---|---|
| 401 | Falta la clave o es inválida |
| 403 | Clave válida sin permiso para esa operación |
| 404 | Producto inexistente, o sin datos en las fuentes de búsqueda |
| 409 | Nombre de producto repetido; o histórico insuficiente para detectar un pico |
| 422 | Parámetros o cuerpo inválidos; o datos rechazados por las reglas de calidad de la ingesta |
| 429 | Demasiadas peticiones (búsqueda) o ingesta demasiado seguida |
| 502 | La API externa falla o devuelve algo ilegible |
| 503 | Ingesta sin configurar (falta `WIKI_USER_AGENT`) o fuente de búsqueda no disponible |
| 500 | Error inesperado: no se devuelve la traza, solo se registra en el log |

## Pruebas

```powershell
python -m pytest -v
```

Los tests **no usan Internet** ni tocan tus datos: trabajan con una copia temporal y sus propias claves.

| Archivo | Qué cubre |
|---|---|
| `test_app.py` | Casos correctos; entradas inválidas (422); recursos inexistentes (404); acceso sin clave o con clave errónea (401); clave sin permiso (403); duplicados (409); persistencia; detector de picos; OpenAPI |
| `test_ingest.py` | Validación y reglas de la ingesta; idempotencia; cambio de fuente; fallos de la API externa (502); datos de mala calidad (422); configuración ausente (503); espera mínima (429); lotes; permisos |
| `test_search.py` | Búsqueda libre: fuentes simuladas, respaldo, caché y límite de peticiones |

## Búsqueda libre

`GET /v1/search?q=calcetines de navidad&months=24` devuelve el interés mensual de cualquier término con fuentes
gratuitas: **Google Trends** (PyTrends; índice relativo 0-100, **no** es el número de búsquedas) y, de respaldo,
**Wikipedia** (visitas al artículo, si existe). Cada respuesta incluye `unit` con el significado del número y
`partial: true` en el mes en curso. PyTrends no es oficial: si Google lo bloquea, se usa Wikipedia o se responde 503.
Los resultados se guardan 1 hora en memoria.

## Estructura

```
├── main.py              # API: endpoints, roles, errores y OpenAPI
├── ingest.py            # Ingesta: API externa → validación → reglas
├── spike.py             # Detector de picos (z-score y crecimiento)
├── search.py            # Búsqueda libre (Trends / Wikipedia, caché)
├── data/products.json   # Datos (20 productos de ejemplo, source "demo")
├── docs/                # Documento de la idea, UML, componentes y flujo de ingesta
├── conftest.py, test_*.py
├── requirements.txt, .env.example, .gitignore
```

## Limitaciones

- Los datos se guardan en un archivo JSON: sirve para esta fase, pero no escala a varias instancias. Siguiente paso: base de datos.
- Los identificadores nuevos continúan desde el mayor existente: si se borra el último y se reinicia el servicio, ese id podría reutilizarse.
- Se mide **interés** (visitas), no ventas; y **no** el número exacto de búsquedas (esos datos son de pago).
- Wikipedia solo cubre temas con artículo; PyTrends no es oficial y puede ser bloqueado.
- Las claves son compartidas por rol: no distinguen entre personas.
- La ingesta es bajo demanda: para actualizarse cada día hay que programarla (ver arriba).

## Correcciones respecto a la entrega anterior

El detalle está en el apartado 12 de [`docs/Documento_proyecto_TrendWatch.docx`](docs/Documento_proyecto_TrendWatch.docx).
En resumen: idea concretada (problema, usuarios, alcance), endpoints/UML/riesgos/planificación incluidos, fuente de datos
oficial en lugar de una librería no oficial, lenguaje preciso ("interés", no "volumen de búsquedas"), y un repositorio
con código ejecutable, ingesta documentada y tests.
