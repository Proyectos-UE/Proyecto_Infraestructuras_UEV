//Para leer el texto bonito pulsa control + shift + v

# Catalog API

Práctica de la Unidad 2 (APIs REST y seguridad) de Infraestructura y
Computación en la Nube.

## De qué va

Hemos montado una API con FastAPI que sirve un catálogo de registros
(id, nombre y categoría). La idea es que otra aplicación pueda consultar los
datos pidiendo solo lo que necesita, sin copiar el archivo entero.

Los datos están en data/records.json. De momento son 30 registros de
ejemplo; falta cambiarlos por los de nuestro grupo.

## Qué hace

- GET /health: comprueba que el servicio funciona.
- GET /v1/records: lista los registros.
- GET /v1/records/{id}: devuelve un registro, o 404 si no existe.
- POST /v1/records y DELETE /v1/records/{id}: crear y borrar.

## Seguridad

Leer es público, pero crear y borrar exige una clave en la cabecera la cual se encuentra en el archivo ADMIN_API_KEY. 
Sin clave o con una incorrecta devuelve 401.
Además se validan los datos de entrada.

## Cómo arrancarla

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ADMIN_API_KEY = "una-clave-larga"
python -m uvicorn main:app --reload
```

Después, abrir http://127.0.0.1:8000/docs para probarla.

## Tests

```powershell
python -m pytest -v
```

Son 9 pruebas: casos que funcionan, un ID que no existe (404), datos
inválidos (422) y el acceso con y sin clave (401).

## Limitaciones

- Los datos viven en memoria: lo que se crea o se borra se pierde al reiniciar
  y no se guarda en el JSON.
- Con varias instancias (por ejemplo en AWS) cada una tendría su propia copia
  de los datos.
- Hay una sola clave compartida, así que no distingue entre usuarios.