# Planificación y riesgos

## Alcance mínimo (MVP)
- Watchlist de términos.
- Ingesta diaria desde Wikipedia.
- Detección de picos y ranking de nichos en ascenso.
- API documentada, dashboard simple, ejecución con `docker compose up`.

Fuera del MVP: alertas por email, redes sociales, APIs de e-commerce, modelo predictivo.

## Fases (ajustar a las fechas reales de entrega)

| Fase | Contenido | Responsables |
|---|---|---|
| 1 | Repo, esqueleto, Docker, CI (hecho) | Todos |
| 2 | Conectores reales + carga de CSV de Google Trends | Alessandro |
| 3 | Backtest con productos virales / no virales; ajuste de umbrales | Eduardo |
| 4 | API completa, validaciones, tests | Jordi |
| 5 | Despliegue en la nube y automatización | Pablo |
| 6 | Dashboard, memoria final, demo | Todos |

## Backtest (cómo demostramos que funciona)
1. Elegir ~5 productos que fueron virales y ~5 que no (con artículo en Wikipedia y CSV de Trends).
2. Ejecutar `find_spikes` sobre su histórico.
3. Medir: días de antelación respecto al pico, falsos positivos y falsos negativos.
4. Ajustar `window`, `z_threshold` y `min_growth` y comparar.

## Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Google bloquea o cambia Trends / PyTrends deja de funcionar | Alto | Fuente principal alternativa (Wikipedia), CSV manual, conector tolerante a fallos |
| Wikipedia no cubre nichos pequeños | Medio | Declarar el límite; añadir YouTube/Reddit en ampliación |
| Interés ≠ ventas | Medio | Dejarlo explícito; futura validación con datos de e-commerce |
| Falsos positivos del detector | Medio | Backtest y umbrales configurables |
| Datos de Trends son relativos (0-100) | Bajo | Usar solo para detectar cambios dentro de una misma serie |
| Desequilibrio de trabajo en el equipo | Medio | PRs con revisión, reparto por áreas, commits individuales |
