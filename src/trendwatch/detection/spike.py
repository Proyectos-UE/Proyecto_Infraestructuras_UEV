"""Detección de picos de interés mediante z-score y crecimiento respecto a la media móvil."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

MIN_STD = 1.0  # evita z-scores enormes en series casi planas


@dataclass(frozen=True)
class SpikeResult:
    is_spike: bool
    z_score: float
    growth: float  # (último - media) / media
    last_value: float
    baseline_mean: float


def _baseline(series: pd.Series, window: int) -> tuple[pd.Series, pd.Series]:
    """Media y desviación de los `window` días ANTERIORES a cada punto."""
    prev = series.shift(1)
    mean = prev.rolling(window, min_periods=max(5, window // 2)).mean()
    std = prev.rolling(window, min_periods=max(5, window // 2)).std().clip(lower=MIN_STD)
    return mean, std


def detect_spike(
    series: pd.Series, window: int = 28, z_threshold: float = 3.0, min_growth: float = 0.5
) -> SpikeResult | None:
    """Evalúa el último punto de la serie. None si no hay histórico suficiente."""
    series = series.dropna().sort_index().astype(float)
    mean, std = _baseline(series, window)
    if series.empty or pd.isna(mean.iloc[-1]):
        return None
    last, m, s = series.iloc[-1], mean.iloc[-1], std.iloc[-1]
    z = (last - m) / s
    growth = (last - m) / max(m, 1e-9)
    return SpikeResult(bool(z >= z_threshold and growth >= min_growth), float(z), float(growth), float(last), float(m))


def find_spikes(
    series: pd.Series, window: int = 28, z_threshold: float = 3.0, min_growth: float = 0.5
) -> pd.DataFrame:
    """Marca todos los días con pico (útil para el backtest)."""
    series = series.dropna().sort_index().astype(float)
    mean, std = _baseline(series, window)
    out = pd.DataFrame({"value": series, "mean": mean, "z_score": (series - mean) / std})
    out["growth"] = (series - mean) / mean.clip(lower=1e-9)
    out["is_spike"] = (out["z_score"] >= z_threshold) & (out["growth"] >= min_growth)
    return out.dropna(subset=["mean"])
