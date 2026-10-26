# Backtest del detector y sus límites

El algoritmo de detección en `src/trendwatch/detection/spike.py` compara
cada observación con datos **anteriores** usando media móvil, desviación
estándar, z-score y crecimiento respecto a la media.

## Prueba automatizada reproducible

```bash
source .venv/bin/activate
python scripts/backtest.py --guardar
```

El script genera **10 series artificiales** de 90 días con semilla 42:
5 presentan un pico creado matemáticamente entre los días 65 y 69;
otras 5 se mantienen estables.

Calculamos verdaderos positivos (TP), falsos positivos (FP), falsos negativos
(FN) y verdaderos negativos (TN) por serie. Un TP requiere detectar un aviso
entre el inicio y el máximo del pico simulado; la anticipación mide días
respecto al **máximo de este pico simulado**, no respecto a una venta real.

Se comparan tres configuraciones de `window`, `z_threshold` y
`min_growth`. Los resultados CSV se guardan en `data/raw/`
(ignorados por Git). El notebook `notebooks/backtest_tendencias.ipynb`
muestra curvas, avisos y métricas.

**Importante:** los números de esta prueba solo verifican el funcionamiento
del código. **No demuestran precisión con productos reales ni capacidad
predictiva comercial.** El siguiente paso científico es seleccionar productos
virales y controles históricos con eventos y fechas documentadas; cargar
series comparables desde Google Trends o Wikipedia y evaluar sin ajustar
umbrales sobre el mismo conjunto de prueba.

## Importación en Python de CSV real de Google Trends

El archivo `scripts/importar_trends_csv.py` permite importar series reales
descargadas manualmente de Google Trends a SQLite o PostgreSQL. Valida todas
las filas y fechas antes de guardarlas. Instrucciones reproducibles en el README.
