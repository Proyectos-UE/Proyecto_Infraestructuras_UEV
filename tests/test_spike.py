import numpy as np
import pandas as pd

from trendwatch.detection.spike import detect_spike, find_spikes


def make_series(values):
    idx = pd.date_range("2026-01-01", periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


def test_detecta_pico_claro():
    rng = np.random.default_rng(0)
    base = list(100 + rng.normal(0, 5, 40))
    res = detect_spike(make_series(base + [400]))
    assert res.is_spike and res.z_score > 3 and res.growth > 1


def test_serie_estable_no_da_pico():
    rng = np.random.default_rng(1)
    res = detect_spike(make_series(100 + rng.normal(0, 5, 41)))
    assert not res.is_spike


def test_historico_insuficiente():
    assert detect_spike(make_series([1, 2, 3])) is None


def test_find_spikes_marca_el_dia_del_pico():
    rng = np.random.default_rng(2)
    values = list(100 + rng.normal(0, 5, 40)) + [500] + list(100 + rng.normal(0, 5, 5))
    out = find_spikes(make_series(values))
    assert out["is_spike"].sum() >= 1
    assert out.index[out["is_spike"]][0] == pd.Timestamp("2026-01-01") + pd.Timedelta(days=40)
