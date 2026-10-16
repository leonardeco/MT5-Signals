import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import lab  # noqa: E402
from research.registry import RegistryError  # noqa: E402

COSTS = {"AAA": {"spread_extra_px": 0.1, "slippage_px": 0.0}, "BBB": {"spread_extra_px": 0.0, "slippage_px": 0.0}}


def trades(n, mean, symbol, seed):
    rng = np.random.default_rng(seed)
    return [{"symbol": symbol, "t": float(i), "r": float(r), "risk_px": 1.0} for i, r in enumerate(rng.normal(mean, 1, n))]


def test_evaluate_discounts_costs_per_symbol():
    tr = trades(50, 0.0, "AAA", 1) + trades(50, 0.0, "BBB", 2)
    res = lab.evaluate("X", tr, n_trials=21, criterio={"t_min": 2}, costs=COSTS)
    assert res["coste_medio_r"] == pytest.approx(0.05)  # 0.1R en la mitad de las operaciones
    gross = np.mean([t["r"] for t in tr])
    assert res["total"]["avg_r"] == pytest.approx(gross - 0.05, abs=1e-3)
    assert set(res["por_simbolo"]) == {"AAA", "BBB"}


def test_evaluate_rejects_noise_and_accepts_strong_edge():
    noise = lab.evaluate("N", trades(300, 0.0, "BBB", 3), 21, {"t_min": 2, "dsr_min": 0.95}, costs=COSTS)
    assert not noise["pasa"] and noise["fallos"]
    edge = lab.evaluate("E", trades(600, 0.4, "BBB", 4), 21,
                        {"t_min": 2, "dsr_min": 0.95, "tramos_positivos": True}, costs=COSTS)
    assert edge["pasa"] and not edge["fallos"]


def test_module_name_and_unregistered_run():
    assert lab.module_name("C-MOTOR-ACTUAL") == "research.hipotesis.c_motor_actual"
    with pytest.raises(RegistryError, match="no está registrada"):
        lab.run("NO-EXISTE-123")
