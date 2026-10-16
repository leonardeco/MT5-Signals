import os
import sys

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk_guardian  # noqa: E402
from database import Base  # noqa: E402
from execution import normalize_volume, validate_levels  # noqa: E402
from signal_engine import QuantSignalEngine  # noqa: E402


def make_df(n: int = 400, start: float = 157.0, drift: float = 0.01, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    closes = start + np.cumsum(rng.normal(drift, 0.05, n))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    wick = np.abs(rng.normal(0, 0.03, n))
    return pd.DataFrame({
        "time": np.arange(n) * 900,
        "open": opens,
        "high": np.maximum(opens, closes) + wick,
        "low": np.minimum(opens, closes) - wick,
        "close": closes,
        "tick_volume": rng.integers(100, 900, n),
    })


# ---------- Volumen y niveles de la orden ----------

def test_normalize_volume_rounds_down_to_step():
    assert normalize_volume(0.237, 0.01, 100, 0.01) == 0.23
    assert normalize_volume(1.29, 0.1, 50, 0.1) == 1.2


def test_normalize_volume_clamps_to_broker_limits():
    assert normalize_volume(0.001, 0.01, 100, 0.01) == 0.01
    assert normalize_volume(500, 0.01, 100, 0.01) == 100


@pytest.mark.parametrize("direction,price,sl,tp,ok", [
    ("BUY", 157.90, 157.50, 158.70, True),
    ("BUY", 157.90, 158.00, 158.70, False),   # SL por encima del precio
    ("SELL", 157.90, 158.30, 157.10, True),
    ("SELL", 157.90, 157.50, 157.10, False),  # SL por debajo del precio
    ("BUY", 157.90, 0.0, 158.70, False),      # sin SL
])
def test_validate_levels_side(direction, price, sl, tp, ok):
    assert (validate_levels(direction, price, sl, tp, 0.0) is None) is ok


def test_validate_levels_respects_broker_min_distance():
    assert validate_levels("BUY", 157.900, 157.895, 158.7, 0.010) is not None
    assert validate_levels("BUY", 157.900, 157.880, 158.7, 0.010) is None


# ---------- Lotaje ----------

def test_lot_size_never_exceeds_risk():
    eng = QuantSignalEngine(risk_percent=1.0)
    # EURUSD sin datos del broker: tick 0.00001 = 1 USD/lote; 1% de 100k = 1000 USD; SL 150 puntos
    lot, exceeds = eng.calculate_lot_size("EURUSD", 0.00150, simulated_equity=100000)
    assert lot == 6.66 and not exceeds
    assert lot * 150 * 1.0 <= 1000


def test_lot_size_flags_min_lot_above_risk():
    eng = QuantSignalEngine(risk_percent=1.0)
    lot, exceeds = eng.calculate_lot_size("XAUUSD", 50.0, simulated_equity=100)
    assert lot == 0.01 and exceeds


# ---------- Motor de señales ----------

def test_signal_pillars_add_up_to_score():
    eng = QuantSignalEngine()
    for seed in range(12):
        df = make_df(seed=seed, drift=0.02 if seed % 2 else -0.02)
        sig = eng.evaluate_dataframes("USDJPY", df, df.copy(), 157.900, 157.902, digits=3, point=0.001)
        assert sig["score"] == min(100, sum(sig["pillars"].values()))


def test_signal_levels_are_on_correct_side():
    eng = QuantSignalEngine()
    for seed in range(30):
        df = make_df(seed=seed, drift=0.03 if seed % 2 else -0.03)
        sig = eng.evaluate_dataframes("USDJPY", df, df.copy(), 157.900, 157.902, digits=3, point=0.001)
        if sig["direction"] == "BUY":
            assert sig["sl"] < sig["entry_price"] < sig["tp"]
        elif sig["direction"] == "SELL":
            assert sig["tp"] < sig["entry_price"] < sig["sl"]
        else:
            assert sig["sl"] == 0.0 and sig["tp"] == 0.0


def test_high_spread_penalizes_score():
    eng = QuantSignalEngine()
    df = make_df(seed=3, drift=0.03)
    normal = eng.evaluate_dataframes("USDJPY", df, df.copy(), 157.900, 157.902, digits=3, point=0.001)
    wide = eng.evaluate_dataframes("USDJPY", df, df.copy(), 157.900, 158.900, digits=3, point=0.001)
    assert wide["score"] == max(0, normal["score"] - 25)


def test_offline_signal_is_never_tradeable():
    import main
    sig = main.offline_signal("USDJPY")
    assert sig["direction"] == "NEUTRAL" and not sig["bot_approved"] and sig["data_source"] == "OFFLINE"


# ---------- Kill switch persistente ----------

def test_kill_switch_state_survives_restart(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(risk_guardian, "SessionLocal", sessionmaker(bind=engine))

    ks = risk_guardian.DailyKillSwitch(max_daily_loss_pct=3.0)
    ks.starting_balance = 100000.0
    ks.state.update(locked=True, lock_reason="prueba")
    ks._save_today()

    restarted = risk_guardian.DailyKillSwitch(max_daily_loss_pct=3.0)
    restarted._load_today()
    assert restarted.starting_balance == 100000.0
    assert restarted.state["locked"] is True
