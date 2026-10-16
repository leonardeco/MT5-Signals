import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
from setups import (  # noqa: E402
    ACTIVADA, EN_ZONA, EXPIRADA, INVALIDADA, PREPARANDO,
    SetupTracker, build_plan, m5_trigger, swing_indices,
)
from signal_engine import QuantSignalEngine  # noqa: E402

ATR = 1.0


def plan_buy(price=101.0, levels=None, recent_lows=(99.5, 99.8), ema21=100.0):
    return build_plan("BUY", ema21, ATR, np.array(recent_lows), np.array([101.5, 101.8]), None,
                      levels if levels is not None else [], price, 3)


# ---------- Plan: zona, SL y objetivos ----------

def test_buy_plan_waits_at_zone_edge_with_structural_sl():
    p = plan_buy(price=101.0, levels=[{"name": "Máximo H1", "price": 104.0}])
    assert p.valid
    assert p.zone_high == pytest.approx(100.2) and p.zone_low == pytest.approx(99.4)
    assert p.entry == pytest.approx(p.zone_high)          # precio aún por encima: se planifica en la zona
    assert p.sl == pytest.approx(min(99.5, 99.4) - 0.25)  # debajo del mínimo/zona con colchón
    assert p.sl < p.zone_low < p.entry < p.tp1 <= p.tp2


def test_plan_rejects_when_liquidity_is_closer_than_1r():
    p = plan_buy(levels=[{"name": "Máximo H1", "price": 100.6}])
    assert not p.valid and p.invalid_kind == "no_space"
    assert "Máximo H1" in p.invalid_reason


def test_plan_is_broken_when_price_crossed_the_sl():
    p = plan_buy(price=98.0)
    assert not p.valid and p.invalid_kind == "broken"


def test_plan_rejects_too_wide_structural_sl():
    p = plan_buy(recent_lows=(95.0, 96.0))
    assert not p.valid and p.invalid_kind == "wide_sl"


def test_plan_without_levels_uses_r_multiples():
    p = plan_buy()
    assert p.valid and p.rr_tp1 == pytest.approx(1.5) and p.rr_tp2 == pytest.approx(3.0)


def test_sell_plan_is_mirror_of_buy():
    p = build_plan("SELL", 100.0, ATR, np.array([98.0, 98.4]), np.array([100.4, 100.5]), None,
                   [{"name": "Mínimo H1", "price": 96.0}], 99.0, 3)
    assert p.valid
    assert p.zone_low == pytest.approx(99.8) and p.zone_high == pytest.approx(100.6)
    assert p.tp2 <= p.tp1 < p.entry < p.zone_high < p.sl


def test_minimum_sl_distance_is_enforced():
    p = plan_buy(price=100.0, recent_lows=(99.95, 99.99), ema21=100.0)
    assert p.entry - p.sl >= 0.75 * ATR - 1e-9


# ---------- Gatillo M5 ----------

def test_bullish_engulfing_inside_zone_triggers():
    p = plan_buy()
    o = np.array([100.5, 100.4, 100.3, 100.1])
    c = np.array([100.4, 100.3, 100.1, 100.35])
    h = np.maximum(o, c) + 0.02
    lo = np.minimum(o, c) - 0.02
    assert m5_trigger(o, h, lo, c, p) == "Envolvente alcista M5"


def test_no_trigger_outside_zone():
    p = plan_buy()
    o = np.array([102.5, 102.4, 102.3, 102.2])
    c = np.array([102.4, 102.3, 102.1, 102.35])
    assert m5_trigger(o, np.maximum(o, c) + 0.02, np.minimum(o, c) - 0.02, c, p) is None


# ---------- Ciclo de vida ----------

def test_tracker_full_lifecycle():
    tr = SetupTracker(ttl=3600, activation_ttl=600)
    p = plan_buy()
    st = tr.update("X", p, 101.0, now=0, signal_bar_close=1000, origin_score=70)
    assert st["state"] == PREPARANDO
    assert tr.update("X", p, 100.1, now=60)["state"] == EN_ZONA
    # un gatillo de una vela que cerró antes que la señal no cuenta
    assert tr.update("X", p, 100.1, now=90, trigger="Envolvente", trigger_bar_close=1000)["state"] == EN_ZONA
    st = tr.update("X", p, 100.1, now=120, trigger="Envolvente alcista M5", trigger_bar_close=1300)
    assert st["state"] == ACTIVADA and st["expires_in"] == 600
    assert tr.update("X", p, 100.1, now=800)["state"] == EXPIRADA


def test_tracker_expires_without_trigger_and_restarts_on_new_signal():
    tr = SetupTracker(ttl=3600)
    p = plan_buy()
    tr.update("X", p, 101.0, now=0, signal_bar_close=1000)
    assert tr.update("X", p, 101.0, now=3601)["state"] == EXPIRADA
    assert tr.live_direction("X") is None
    st = tr.update("X", p, 101.0, now=3700, signal_bar_close=5000)
    assert st["state"] == PREPARANDO


def test_tracker_invalidation_is_sticky():
    tr = SetupTracker()
    tr.update("X", plan_buy(), 101.0, now=0, signal_bar_close=1000)
    assert tr.update("X", plan_buy(price=98.0), 98.0, now=10)["state"] == INVALIDADA
    assert tr.update("X", plan_buy(), 101.0, now=20)["state"] == INVALIDADA


def test_activation_expires_if_price_runs_away():
    tr = SetupTracker()
    p = plan_buy()
    tr.update("X", p, 100.1, now=0, signal_bar_close=1000)
    tr.update("X", p, 100.1, now=10, trigger="Pin bar alcista M5", trigger_bar_close=1300)
    assert tr.update("X", p, 100.1 + 0.6 * p.risk, now=20)["state"] == EXPIRADA


# ---------- Swings ----------

def test_swing_indices_find_confirmed_pivots():
    highs = np.array([1, 2, 5, 2, 1, 2, 3, 2, 1], float)
    lows = highs - 1
    sh, sl = swing_indices(highs, lows, k=2)
    assert list(sh) == [2, 6]
    assert 4 in sl


# ---------- Simulación del backtest ----------

def m5_bars(rows):
    arr = np.array(rows, float)
    return {"open": arr[:, 0], "high": arr[:, 1], "low": arr[:, 2], "close": arr[:, 3],
            "spread_px": np.zeros(len(arr))}


def test_simulate_stop_first_when_same_bar_hits_both():
    m5 = m5_bars([[100, 103, 98, 100]])
    assert backtest.simulate_trade("BUY", 100, 99, 101, 102, m5, 0, partial=True)["r"] == -1.0


def test_simulate_tp1_then_breakeven():
    m5 = m5_bars([[100, 101.2, 99.6, 101], [101, 101.1, 99.9, 100]])
    res = backtest.simulate_trade("BUY", 100, 99, 101, 103, m5, 0, partial=True)
    assert res["outcome"] == "TP1+BE" and res["r"] == pytest.approx(0.5)


def test_simulate_tp1_then_tp2():
    m5 = m5_bars([[100, 101.2, 99.6, 101], [101, 103.5, 100.5, 103]])
    res = backtest.simulate_trade("BUY", 100, 99, 101, 103, m5, 0, partial=True)
    assert res["outcome"] == "TP2" and res["r"] == pytest.approx(0.5 * 1 + 0.5 * 3)


def test_simulate_sell_uses_ask_for_exits():
    m5 = m5_bars([[100, 100.5, 99.5, 100]])
    m5["spread_px"][:] = 0.6  # el ask (high + spread) toca el SL de 101
    assert backtest.simulate_trade("SELL", 100, 101, 98, 97, m5, 0, partial=True)["outcome"] == "SL"


# ---------- Integración: motor + backtest sobre datos sintéticos ----------

def synthetic(n, seconds, start=157.0, seed=0, drift=0.0):
    rng = np.random.default_rng(seed)
    close = start + np.cumsum(rng.normal(drift, 0.05 * np.sqrt(seconds / 900), n))
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0, 0.03, n))
    t0 = 1_700_000_000 - (1_700_000_000 % 86400)
    return pd.DataFrame({
        "time": t0 + np.arange(n) * seconds,
        "open": open_, "high": np.maximum(open_, close) + wick, "low": np.minimum(open_, close) - wick,
        "close": close, "tick_volume": rng.integers(100, 900, n), "spread": np.full(n, 2),
    })


def test_engine_live_path_returns_plan_fields():
    eng = QuantSignalEngine()
    for seed in range(40):
        m15 = synthetic(400, 900, seed=seed, drift=0.02 if seed % 2 else -0.02)
        h1 = synthetic(400, 3600, seed=seed + 100, drift=0.08 if seed % 2 else -0.08)
        m5 = synthetic(60, 300, start=float(m15["close"].iloc[-1]), seed=seed)
        res = eng.evaluate_dataframes("USDJPY", m15, h1, float(m5["close"].iloc[-1]),
                                      float(m5["close"].iloc[-1]) + 0.002, digits=3, point=0.001,
                                      df_m5=m5, now=0.0)
        assert "state" in res
        if res["direction"] != "NEUTRAL" and res["state"] not in ("SIN_SETUP", "DESCARTADA", "INVALIDADA"):
            if res["direction"] == "BUY":
                assert res["sl"] < res["zone_low"] <= res["zone_high"] and res["tp1"] <= res["tp"]
            else:
                assert res["tp"] <= res["tp1"] and res["zone_low"] <= res["zone_high"] < res["sl"]
            return
    pytest.skip("ninguna semilla generó un setup válido")


def test_backtest_frames_runs_and_funnel_is_consistent():
    frames = {
        "m15": synthetic(2500, 900, seed=1, drift=0.01),
        "h1": synthetic(1200, 3600, seed=2, drift=0.04),
        "m5": synthetic(6000, 300, seed=3, drift=0.003),
        "d1": synthetic(80, 86400, seed=4),
        "w1": synthetic(20, 7 * 86400, seed=5),
    }
    # M5 debe empezar después del calentamiento de M15/H1
    frames["m5"]["time"] += 900 * 600
    res = backtest.backtest_frames(frames, point=0.001, digits=3)
    f = res["nuevo"]["funnel"]
    assert res["nuevo"]["n"] == f["activadas"]
    assert f["setups"] >= f["activadas"] + f["invalidadas"] + f["expiradas"] + f["sin_espacio"] - 1
    assert res["anterior"]["n"] >= 0


# ---------- Variantes investigadas (research/INFORME_VARIANTES.md) ----------

def test_structure_break_alone_no_longer_triggers():
    """Vela alcista en zona que solo rompe los máximos previos (sin envolvente ni pin bar): ya no es gatillo."""
    p = plan_buy()
    o = np.array([100.05, 100.10, 100.08, 100.00])
    c = np.array([100.10, 100.08, 100.12, 100.20])
    h = np.array([100.15, 100.14, 100.15, 100.22])
    lo = np.array([100.00, 100.05, 100.04, 99.98])
    assert c[-1] > h[:-1].max() and c[-1] > o[-1]          # la condición de ruptura se cumple
    assert m5_trigger(o, h, lo, c, p) is None


def test_bearish_structure_break_alone_no_longer_triggers():
    p = build_plan("SELL", 100.0, ATR, np.array([98.0, 98.4]), np.array([100.4, 100.5]), None,
                   [{"name": "Mínimo H1", "price": 96.0}], 99.0, 3)
    o = np.array([99.95, 99.90, 99.92, 100.00])
    c = np.array([99.90, 99.92, 99.88, 99.80])
    h = np.array([100.00, 99.95, 99.96, 100.02])
    lo = np.array([99.85, 99.86, 99.85, 99.78])
    assert c[-1] < lo[:-1].min() and c[-1] < o[-1]
    assert m5_trigger(o, h, lo, c, p) is None


def test_pin_bar_still_triggers():
    p = plan_buy()
    o = np.array([100.5, 100.4, 100.3, 100.15])
    c = np.array([100.4, 100.3, 100.2, 100.18])
    h = np.array([100.55, 100.45, 100.35, 100.20])
    lo = np.array([100.35, 100.25, 100.15, 99.90])
    assert m5_trigger(o, h, lo, c, p) == "Pin bar alcista M5"


def _bt_frames():
    frames = {
        "m15": synthetic(2500, 900, seed=1, drift=0.01),
        "h1": synthetic(1200, 3600, seed=2, drift=0.04),
        "m5": synthetic(6000, 300, seed=3, drift=0.003),
        "d1": synthetic(80, 86400, seed=4),
        "w1": synthetic(20, 7 * 86400, seed=5),
    }
    frames["m5"]["time"] += 900 * 600
    return frames


CACHE_180 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "research", "cache", "frames_180d.pkl")


@pytest.mark.skipif(not os.path.exists(CACHE_180), reason="sin caché de MT5 (python research/cache_frames.py 180)")
def test_backtest_hooks_are_neutral_on_real_history():
    import pickle
    with open(CACHE_180, "rb") as fh:
        v = pickle.load(fh)["EURUSD"]
    plain = backtest.backtest_frames(v["frames"], v["point"], v["digits"])
    hooked = backtest.backtest_frames(v["frames"], v["point"], v["digits"], setup_filter=lambda i, d, s: True,
                                      trigger_filter=lambda t: True)
    assert plain["nuevo"]["n"] > 0
    assert plain["nuevo"] == hooked["nuevo"]
    assert all("Ruptura" not in t["trigger"] for t in plain["trades_nuevo"])


def test_backtest_setup_filter_can_reject_everything():
    res = backtest.backtest_frames(_bt_frames(), point=0.001, digits=3, setup_filter=lambda i, d, s: False)
    assert res["nuevo"]["n"] == 0 and res["nuevo"]["funnel"]["setups"] == 0


# ---------- Costes (constitución, principio 2) ----------

@pytest.mark.skipif(not os.path.exists(CACHE_180), reason="sin caché de MT5 (python research/cache_frames.py 180)")
def test_backtest_costs_reduce_each_trade_by_cost_over_risk():
    import pickle
    with open(CACHE_180, "rb") as fh:
        v = pickle.load(fh)["EURUSD"]
    gross = backtest.backtest_frames(v["frames"], v["point"], v["digits"])
    net = backtest.backtest_frames(v["frames"], v["point"], v["digits"], cost_px=0.00005)
    assert gross["trades_nuevo"] and len(net["trades_nuevo"]) == len(gross["trades_nuevo"])
    for g, n in zip(gross["trades_nuevo"], net["trades_nuevo"]):
        assert n["r"] == pytest.approx(g["r"] - 0.00005 / g["risk_px"])
    assert net["nuevo"]["avg_r"] < gross["nuevo"]["avg_r"]
    assert net["costes"]["extra_px"] == 0.00005 and net["costes"]["medio_r_nuevo"] > 0
    assert gross["costes"] == {"extra_px": 0.0, "medio_r_nuevo": 0.0}
