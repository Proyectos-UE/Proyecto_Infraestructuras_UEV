"""Backtest REPRODUCIBLE y SINTÉTICO: no demuestra precisión con datos reales."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trendwatch.detection.spike import find_spikes  # noqa: E402

INICIO = pd.Timestamp("2026-01-01")
DIAS = 90
DIA_INICIO_PICO = 65
DIA_MAXIMO = 69


def crear_casos() -> list[tuple[str, pd.Series, bool]]:
    """Cinco series con picos artificiales y cinco controles estables."""
    rng = np.random.default_rng(42)
    fechas = pd.date_range(INICIO, periods=DIAS, freq="D")
    casos = []
    for numero in range(10):
        valores = 35 + numero * 3 + rng.normal(0, 2, DIAS)
        valores = np.maximum(valores, 1)
        viral = numero < 5
        if viral:
            valores[DIA_INICIO_PICO:DIA_MAXIMO + 1] += np.array([22, 35, 48, 62, 75])
            valores[DIA_MAXIMO + 1:] += 6
        etiqueta = f"Ejemplo sintetico {numero + 1:02d}"
        casos.append((etiqueta, pd.Series(valores, index=fechas), viral))
    return casos


def evaluar(window: int = 28, z_threshold: float = 3.0, min_growth: float = 0.5):
    """Resultados por producto: positivos antes o durante un pico artificial."""
    if window < 7 or z_threshold <= 0 or min_growth < 0:
        raise ValueError("Parámetros inválidos del detector")

    filas = []
    for nombre, serie, es_viral in crear_casos():
        detecciones = find_spikes(
            serie, window=window, z_threshold=z_threshold, min_growth=min_growth
        )
        dias_alerta = [
            int((fecha - INICIO).days)
            for fecha in detecciones.index[detecciones["is_spike"]]
        ]
        validas = [dia for dia in dias_alerta if DIA_INICIO_PICO <= dia <= DIA_MAXIMO]
        tp = bool(es_viral and validas)
        fp = bool((not es_viral) and dias_alerta)
        fn = bool(es_viral and not validas)
        anticipacion = DIA_MAXIMO - validas[0] if tp else None
        filas.append({
            "producto": nombre,
            "tipo": "pico sintetico" if es_viral else "control estable",
            "alertas": len(dias_alerta),
            "verdadero_positivo": int(tp),
            "falso_positivo": int(fp),
            "falso_negativo": int(fn),
            "anticipacion_dias": anticipacion,
        })
    return pd.DataFrame(filas)


def resumen(resultado: pd.DataFrame) -> dict:
    tp = int(resultado["verdadero_positivo"].sum())
    fp = int(resultado["falso_positivo"].sum())
    fn = int(resultado["falso_negativo"].sum())
    tn = len(resultado) - tp - fp - fn
    return {
        "TP": tp, "FP": fp, "FN": fn, "TN": tn,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "anticipacion_media_dias": round(
            float(resultado["anticipacion_dias"].dropna().mean()), 2
        ) if tp else None,
    }


def comparar() -> pd.DataFrame:
    filas = []
    for window, z, growth in [(14, 2.5, 0.4), (28, 3.0, 0.5), (42, 3.5, 0.6)]:
        metricas = resumen(evaluar(window, z, growth))
        filas.append({"window": window, "z_threshold": z, "min_growth": growth, **metricas})
    return pd.DataFrame(filas)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--guardar", action="store_true", help="Guardar los CSV locales")
    args = parser.parse_args()
    datos = evaluar()
    tabla = comparar()
    print("BACKTEST SINTETICO — NO REPRESENTA PRECISION CON DATOS REALES")
    print(datos.to_string(index=False))
    print("\nMetricas:", resumen(datos))
    print("\nComparacion de parametros:\n", tabla.to_string(index=False))
    if args.guardar:
        salida = ROOT / "data" / "raw"
        salida.mkdir(parents=True, exist_ok=True)
        datos.to_csv(salida / "backtest_sintetico.csv", index=False)
        tabla.to_csv(salida / "comparacion_parametros.csv", index=False)
        print("\nCSV guardados en data/raw/ (ignorados por Git)")


if __name__ == "__main__":
    main()
