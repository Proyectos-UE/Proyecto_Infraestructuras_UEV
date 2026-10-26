# Cómo trabajamos en el repositorio

## Ramas

- `main` se mantiene **vacía**, como ha indicado el profesor. No enviar allí los archivos del proyecto.
- `test` es la rama que contiene la versión integrada del proyecto y que usamos para verificar las entregas.
- Cada tarea nueva se trabaja en su propia rama: `feat/<tema>`, `fix/<tema>` o `docs/<tema>`, partiendo de `test`.
- Al terminar, hacemos un Pull Request hacia `test` y revisamos que pasen las pruebas automáticas antes de fusionar.
- No se deben sobrescribir cambios locales de otra persona ni subir `.env` con secretos.

## Antes de hacer un Pull Request

```bash
python -m pytest -q
docker compose config -q
```

En el primer arranque se puede crear una configuración privada mediante
`python scripts/preparar_config.py`, y ejecutar los servicios con
`docker compose up --build`.

## Reparto inicial

| Área | Responsable | Carpeta |
|---|---|---|
| Conectores y datos | Alessandro | `src/trendwatch/connectors/` |
| Detector y backtest | Eduardo | `src/trendwatch/detection/`, `notebooks/`, `scripts/backtest.py` |
| API y base de datos | Jordi | `src/trendwatch/api/`, `models.py`, `services.py` |
| Infraestructura y despliegue | Pablo | `Dockerfile`, `docker-compose.yml`, `.github/` |

*El reparto es orientativo y puede ajustarse en el equipo.*
