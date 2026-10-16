"""Mecánica de H-A y H-B sobre datos sintéticos (sin mirar resultados reales antes de evaluarlas)."""
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from costs import swap_cost_px_per_night  # noqa: E402
from research.hipotesis import h_a, h_b  # noqa: E402

DAY0 = 1_767_225_600  # 2026-01-01 00:00 (epoch tratado como hora del servidor)


def m15_days(n_days, overrides):
    """Velas M15 planas en 100 con rango 1; overrides[(día, 'HH:MM')] = dict de campos a cambiar."""
    rows = []
    for d in range(n_days):
        for q in range(96):
            hm = f"{q // 4:02d}:{(q % 4) * 15:02d}"
            row = {"time": DAY0 + d * 86400 + q * 900, "open": 100.0, "high": 100.5, "low": 99.5,
                   "close": 100.0, "spread": 10}
            row.update(overrides.get((d, hm), {}))
            rows.append(row)
    return pd.DataFrame(rows)


def test_h_a_buys_after_positive_first_half_hour_and_exits_at_close():
    df = m15_days(2, {(1, "16:45"): {"close": 101.0, "high": 101.5},
                      (1, "22:45"): {"close": 100.8, "high": 101.0}})
    trades = h_a.trades_from_m15(df, point=0.01)
    assert len(trades) == 1
    t = trades[0]
    atr = float(h_a.wilder_atr(df).iloc[1 * 96 + 89])  # vela 22:15 del día 2
    entry = 100.0 + 0.10  # apertura 22:30 + spread
    assert t["dir"] == "BUY" and t["risk_px"] == pytest.approx(2 * atr)
    assert t["r"] == pytest.approx((100.8 - entry) / (2 * atr))


def test_h_a_sells_after_negative_first_half_hour_and_respects_stop():
    df = m15_days(2, {(1, "16:45"): {"close": 99.0, "low": 98.5},
                      (1, "22:30"): {"high": 110.0}})
    t = h_a.trades_from_m15(df, point=0.01)[0]
    assert t["dir"] == "SELL" and t["r"] == pytest.approx(-1.0)


def test_h_a_skips_days_without_previous_complete_day_or_flat_r1():
    assert h_a.trades_from_m15(m15_days(1, {(0, "16:45"): {"close": 101.0}}), point=0.01) == []
    assert h_a.trades_from_m15(m15_days(2, {}), point=0.01) == []  # r1 = 0
    incomplete = m15_days(3, {(2, "16:45"): {"close": 101.0}})
    incomplete = incomplete[~((incomplete["time"] >= DAY0 + 86400 + 16 * 3600) &
                              (incomplete["time"] < DAY0 + 86400 + 17 * 3600))]  # día 2 sin 16:45
    assert h_a.trades_from_m15(incomplete, point=0.01) == []


def d1_series(closes, spread_pts=0):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({"time": DAY0 + np.arange(n) * 86400, "open": opens, "close": closes,
                         "high": np.maximum(opens, closes), "low": np.minimum(opens, closes), "spread": spread_pts})


SPEC = {"point": 0.01, "contract_size": 100.0, "swap_mode": 1, "swap_long": -10.0, "swap_short": 5.0}


def test_h_b_follows_12_month_sign_with_vol_scaled_r_and_swap():
    rng = np.random.default_rng(0)
    closes = 100 * np.cumprod(1 + 0.002 + rng.normal(0, 0.005, 400))
    df = d1_series(closes)
    trades = h_b.tsmom_trades(df, "XAUUSD", SPEC)
    expected_n = len(range(252, len(df) - 1 - 21, 21))
    assert len(trades) == expected_n and all(t["dir"] == "BUY" for t in trades)
    first = trades[0]
    k = 252
    sigma = np.std((closes[1:] / closes[:-1] - 1)[k - 63:k], ddof=1)
    entry, exit_ = df["open"][k + 1], df["open"][k + 22]
    swap = 21 * 0.10  # 21 noches naturales × 10 puntos × 0.01
    assert first["swap_px"] == pytest.approx(swap)
    assert first["risk_px"] == pytest.approx(entry * sigma * math.sqrt(21))
    assert first["r"] == pytest.approx((exit_ - entry - swap) / first["risk_px"])


def test_h_b_shorts_downtrend_and_positive_swap_is_not_income():
    closes = 100 * np.cumprod(np.full(320, 0.998) + np.tile([0.004, -0.004], 160))
    trades = h_b.tsmom_trades(d1_series(closes), "XAUUSD", SPEC)
    assert trades and all(t["dir"] == "SELL" and t["swap_px"] == 0.0 for t in trades)


def test_swap_cost_conversion_by_mode():
    assert swap_cost_px_per_night({"swap_mode": 1, "point": 0.01, "swap_long": -12.6, "swap_short": 3}, "BUY") == pytest.approx(0.126)
    assert swap_cost_px_per_night({"swap_mode": 1, "point": 0.01, "swap_long": -12.6, "swap_short": 3}, "SELL") == 0.0
    assert swap_cost_px_per_night({"swap_mode": 3, "contract_size": 1.0, "swap_long": -0.82, "swap_short": -0.75}, "SELL") == pytest.approx(0.75)
    with pytest.raises(ValueError):
        swap_cost_px_per_night({"swap_mode": 5, "swap_long": -1, "swap_short": -1}, "BUY")
