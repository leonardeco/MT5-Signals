import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import costs  # noqa: E402


def test_extra_cost_sums_components():
    c = {"X": {"spread_extra_px": 0.2, "slippage_px": 0.1, "commission_usd_per_lot": 7.0, "contract_size": 100.0}}
    assert costs.extra_cost_px("X", costs=c) == pytest.approx(0.2 + 0.1 + 0.07)


def test_commission_for_jpy_quoted_symbol_uses_price():
    c = {"USDJPY": {"spread_extra_px": 0.0, "slippage_px": 0.0, "commission_usd_per_lot": 7.0,
                    "contract_size": 100000.0, "quote_in_usd": False}}
    # 7 USD por lote = 7 * 150 JPY = 1050 JPY / 100 000 unidades = 0.0105 de precio
    assert costs.extra_cost_px("USDJPY", price=150.0, costs=c) == pytest.approx(0.0105)


def test_unknown_symbol_costs_nothing():
    assert costs.extra_cost_px("NADA", costs={}) == 0.0


def test_apply_costs_converts_price_cost_to_r():
    trades = [{"r": 1.0, "risk_px": 2.0}, {"r": -1.0, "risk_px": 0.5}, {"r": 0.3}]
    net = costs.apply_costs(trades, 0.1)
    assert [t["r"] for t in net] == pytest.approx([0.95, -1.2, 0.3])
    assert net[0]["r_bruto"] == 1.0 and trades[0]["r"] == 1.0  # no modifica la lista original


def test_costes_json_overrides_defaults(tmp_path):
    p = tmp_path / "costes.json"
    p.write_text(json.dumps({"simbolos": {"XAUUSD": {"slippage_px": 0.5}}}), encoding="utf-8")
    c = costs.load_costs(p)
    assert c["XAUUSD"]["slippage_px"] == 0.5 and c["XAUUSD"]["spread_extra_px"] == 0.24
    assert costs.load_costs(tmp_path / "no_existe.json") == costs.DEFAULT_COSTS


# ---------- Medición de spreads y caché de historial (research/data.py) ----------

def test_spread_stats_measures_gap_between_ticks_and_bars():
    import numpy as np
    from research.data import spread_stats
    st = spread_stats(np.array([0.0, 0.3, 0.4, 0.4, 0.5]), np.array([0.1, 0.15, 0.2]))
    assert st["ticks"] == 4 and st["tick_p50"] == pytest.approx(0.4) and st["bar_p50"] == pytest.approx(0.15)
    assert st["spread_extra_px"] == pytest.approx(0.25)
    assert spread_stats(np.array([0.0]), np.array([0.1])) == {"ticks": 0}


def test_merge_rates_dedups_and_sorts():
    import pandas as pd
    from research.data import merge_rates
    old = pd.DataFrame({"time": [1, 2, 3], "close": [1.0, 2.0, 3.0]})
    new = pd.DataFrame({"time": [3, 4], "close": [3.5, 4.0]})
    m = merge_rates(old, new)
    assert m["time"].tolist() == [1, 2, 3, 4] and m["close"].tolist() == [1.0, 2.0, 3.5, 4.0]
    assert merge_rates(None, new)["time"].tolist() == [3, 4]
