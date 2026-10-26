# Cómo trabajamos

## Ramas
- `main` siempre funciona y está protegida: **nadie hace push directo**.
- Cada tarea, una rama: `feat/<tema>`, `fix/<tema>`, `docs/<tema>`.
- Se integra con **Pull Request** y al menos **1 revisión** de otra persona del equipo.
- El CI (tests + build de Docker) debe pasar antes de hacer merge.

## Commits
Mensajes en imperativo y descriptivos: `Añade conector de Wikipedia`, no `cambios` ni `update`.
Commits pequeños y frecuentes, cada uno con su propia autoría.

## Antes de abrir un PR
```bash
pytest
```

## Reparto de áreas

| Área | Responsable | Carpeta principal |
|---|---|---|
| Conectores y datos | Alessandro | `src/trendwatch/connectors/` |
| Detector y backtest | Eduardo | `src/trendwatch/detection/`, `notebooks/` |
| API y base de datos | Jordi | `src/trendwatch/api/`, `models.py`, `services.py` |
| Infraestructura y despliegue | Pablo | `Dockerfile`, `docker-compose.yml`, `.github/` |

*(Reparto inicial propuesto; cambiadlo entre vosotros si preferís otro.)*
