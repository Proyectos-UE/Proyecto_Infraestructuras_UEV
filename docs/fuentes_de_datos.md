# Fuentes de datos

## Resumen

| Fuente | Rol | Estado | Coste | Clave API |
|---|---|---|---|---|
| Wikimedia Pageviews API | Fuente principal en vivo | Oficial | Gratis | No (requiere User-Agent identificable) |
| Google Trends (CSV exportado) | Histórico y backtest | Manual, estable | Gratis | No |
| PyTrends | Extra opcional | **No oficial y archivado** | Gratis | No |
| YouTube Data API / Reddit | Ampliación futura | Oficial | Cuota gratuita | Sí |

## Por qué no dependemos solo de PyTrends
PyTrends es una librería no oficial cuyo repositorio fue archivado en 2025. Google
limita agresivamente las peticiones automáticas (errores HTTP 429) y cambia sus
endpoints internos sin aviso. Por eso:
- el conector de PyTrends está **desactivado por defecto** (`ENABLE_PYTRENDS=false`);
- si falla, devuelve una lista vacía y **no rompe el worker**;
- el sistema funciona con Wikipedia aunque Google bloquee.

## Qué mide cada fuente
- **Wikipedia:** visitas diarias reales a un artículo (conteo absoluto). Solo cubre términos con artículo.
- **Google Trends:** interés **relativo** de 0 a 100 dentro del rango consultado. **No es volumen de búsquedas.**
  Dos series de Trends no son comparables entre sí salvo que se descarguen en la misma consulta.

## Condiciones de uso
- Wikimedia exige un `User-Agent` con datos de contacto y pide un uso razonable (no hacer ráfagas de peticiones).
  Configúralo en `WIKI_USER_AGENT`.
- Los CSV de Google Trends se descargan desde la web pública de Trends y se guardan en `data/raw/` (no se versionan).
- Antes de integrar APIs de redes sociales hay que revisar sus términos y cuotas.

## Medición de interés y no de ventas
Un pico de interés no implica un pico de compras. El sistema detecta **atención**, y esa limitación debe
constar en la memoria.
