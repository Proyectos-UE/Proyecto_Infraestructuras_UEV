# TrendWatch API

Práctica de la Unidad 2 (APIs REST y seguridad) de Infraestructura y
Computación en la Nube, adaptada a nuestro proyecto de grupo.

**Equipo:** Pablo Díaz · Eduardo Caicedo · Jordi Aguado · Alessandro Matos

## De qué va

Hemos montado una API con FastAPI que sirve una lista de productos y nichos de
mercado vigilados (nombre, categoría y serie diaria de interés) y detecta cuándo
el interés de uno se dispara respecto a su media reciente. La idea es que otra
aplicación pueda consultar solo lo que necesita (una categoría, la serie de un
producto o si tiene pico ahora) sin copiar el archivo entero.

Los datos están en `data/products.json`. **De momento son 20 productos con datos
de demostración generados a mano** (campo `source: "demo"`): hay que sustituirlos
por datos reales con `python fetch_data.py` (ver «Datos»).

## Qué hace

- `GET /health`: comprueba que el servicio funciona.
- `GET /v1/products`: lista los productos (filtro `category`, `limit`, `offset`).
- `GET /v1/products/{id}`: devuelve un producto, o 404 si no existe.
- `GET /v1/products/{id}/series`: su serie diaria de interés (`days`).
- `GET /v1/products/{id}/spike`: dice si el último dato es un pico (z-score y crecimiento).
- `GET /v1/rankings/rising`: productos ordenados por crecimiento.
- `POST /v1/products` y `DELETE /v1/products/{id}`: crear y borrar.
- `GET /v1/admin/summary`: resumen protegido.

## Seguridad

Leer es público, pero crear, borrar y ver el resumen exige una clave en la
cabecera `X-API-Key`, que se define en la variable de entorno `ADMIN_API_KEY`.
Sin clave o con una incorrecta devuelve 401. La API no arranca si no está definida.
Además se validan los datos de entrada (longitudes, campos desconocidos, fechas
repetidas) y el archivo de datos se valida al arrancar.

La clave **no se sube a GitHub** (`.gitignore` excluye `.env` y `ADMIN_API_KEY.txt`).

## Cómo arrancarla

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ADMIN_API_KEY = "una-clave-larga"
python -m uvicorn main:app --reload
```

Después, abrir http://127.0.0.1:8000/docs para probarla. El botón **Authorize**
permite pegar la clave para los endpoints protegidos.

## Datos

El interés se mide con las **visitas diarias a artículos de Wikipedia** (API
oficial y gratuita de Wikimedia). Para generar `data/products.json` con datos reales:

```powershell
$env:WIKI_USER_AGENT = "TrendWatch/0.1 (proyecto universitario; contacto: tu_email@ejemplo.com)"
python fetch_data.py          # últimos 90 días
```

La lista de productos está al principio de `fetch_data.py`. Los que no tengan
artículo con ese título se omiten y se avisa; se puede indicar el título exacto
como tercer valor. Tras regenerar, reiniciar la API.

## Tests

```powershell
python -m pytest -v
```

Son 23 pruebas: casos que funcionan, un ID que no existe (404), datos inválidos
(422), el acceso con y sin clave (401), duplicados (409), la detección de picos y la
lectura de la respuesta de Wikipedia (simulada, sin Internet).

## Limitaciones

- Los datos viven en memoria: lo que se crea o se borra se pierde al reiniciar
  y no se guarda en el JSON.
- Con varias instancias (por ejemplo en AWS) cada una tendría su propia copia de los datos.
- Hay una sola clave compartida, así que no distingue entre usuarios.
- Se mide **interés**, no ventas: un pico de visitas no implica un pico de compras.
- Wikipedia solo cubre productos o temas que tengan artículo.
- Los datos `demo` no son reales.

## Siguientes pasos del proyecto

Guardar los datos en una base de datos, recogerlos cada día de forma automática,
añadir otras fuentes (por ejemplo Google Trends), desplegar con Docker en la nube y
validar el detector con productos que ya fueron virales.
