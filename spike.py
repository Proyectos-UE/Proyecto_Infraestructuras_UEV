"""Detector de picos: compara el último valor con la media de los días anteriores."""
from statistics import mean, stdev

MIN_STD = 1.0  # evita z-scores enormes en series casi planas


def analyze(
    values: list[float], window: int = 28, z_threshold: float = 3.0, min_growth: float = 0.5
) -> dict | None:
    """Evalúa el último valor de la serie.

    Devuelve None si no hay histórico suficiente. Hay pico cuando el último valor
    supera la media de los `window` días anteriores en `z_threshold` desviaciones
    y, además, crece al menos `min_growth` (0.5 = +50 %) respecto a esa media.
    """
    previous = values[-(window + 1) : -1]
    if len(previous) < max(5, window // 2):
        return None
    baseline = mean(previous)
    spread = max(stdev(previous), MIN_STD)
    last = values[-1]
    z_score = (last - baseline) / spread
    growth = (last - baseline) / max(baseline, 1e-9)
    return {
        "is_spike": z_score >= z_threshold and growth >= min_growth,
        "z_score": z_score,
        "growth": growth,
        "last_value": last,
        "baseline_mean": baseline,
    }
