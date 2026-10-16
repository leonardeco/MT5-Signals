import os
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import journal  # noqa: E402


def test_excursions_buy_and_sell():
    assert journal.excursions_r("BUY", 100.0, 98.0, [101.0, 103.0], [99.0, 100.5]) == (0.5, 1.5)
    assert journal.excursions_r("SELL", 100.0, 102.0, [101.0, 100.2], [97.0, 99.0]) == (0.5, 1.5)
    assert journal.excursions_r("BUY", 100.0, 100.0, [101.0], [99.0]) == (None, None)


def test_r_from_profit():
    assert journal.r_from_profit(-50.0, 50.0) == -1.0 and journal.r_from_profit(10.0, None) is None


def test_finalize_closed_trade_uses_risk_money_and_m1_path():
    class FakeMT5:
        ORDER_TYPE_BUY, ORDER_TYPE_SELL, TIMEFRAME_M1 = 0, 1, 1

        def order_calc_profit(self, kind, sym, vol, price, sl):
            return -(price - sl) * vol * 100000

        def copy_rates_range(self, sym, tf, a, b):
            return {"high": np.array([1.1010, 1.1030]), "low": np.array([1.0995, 1.1005])}

    trade = SimpleNamespace(ticket=1, direction="BUY", entry_price=1.1000, sl_initial=1.0990, volume_initial=0.1,
                            profit=15.0, r_multiple=None, mae_r=None, mfe_r=None)
    deals = [SimpleNamespace(symbol="EURUSD", time=1_000), SimpleNamespace(symbol="EURUSD", time=2_000)]
    journal.finalize_closed_trade(trade, deals, FakeMT5())
    assert trade.r_multiple == pytest.approx(1.5)            # 15 / (0.0010 × 0.1 × 100000 = 10)
    assert (trade.mae_r, trade.mfe_r) == (0.5, 3.0)


def test_stats_group_split_legs_into_one_plan_and_compare_with_backtest():
    trades = [
        {"ticket": 1, "symbol": "EURUSD", "group_id": 1, "volume": 0.1, "r_multiple": 1.5, "mae_r": 0.2, "mfe_r": 1.6, "slippage_px": 0.00002},
        {"ticket": 2, "symbol": "EURUSD", "group_id": 1, "volume": 0.1, "r_multiple": 0.0, "mae_r": 0.3, "mfe_r": 1.6, "slippage_px": 0.0},
        {"ticket": 3, "symbol": "XAUUSD", "group_id": None, "volume": 0.2, "r_multiple": -1.0, "mae_r": 1.0, "mfe_r": 0.1, "slippage_px": None},
        {"ticket": 4, "symbol": "XAUUSD", "group_id": None, "volume": 0.2, "r_multiple": None},  # sin datos: fuera
    ]
    st = journal.journal_stats(trades, {"EURUSD": -0.1})
    assert st["n"] == 2 and st["expectancy_r"] == pytest.approx((0.75 - 1.0) / 2, abs=1e-3)
    assert st["win_rate"] == 50.0 and st["avg_slippage_px"] == pytest.approx(0.00001)
    assert st["by_symbol"]["EURUSD"] == {"n": 1, "expectancy_r": 0.75, "backtest_avg_r": -0.1}
    assert st["by_symbol"]["XAUUSD"]["backtest_avg_r"] is None


def test_stats_empty():
    assert journal.journal_stats([], {})["n"] == 0
