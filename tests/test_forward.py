import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import forward  # noqa: E402
from research.hipotesis import h_b  # noqa: E402


def test_freeze_once_and_detect_rule_changes(tmp_path):
    for f in forward.RULE_FILES:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("x = 1\n", encoding="utf-8")
    cfg_path = tmp_path / "forward_config.json"
    cfg = forward.freeze(tmp_path, cfg_path, now=datetime(2026, 10, 15, tzinfo=timezone.utc))
    assert forward.changed_rules(cfg, tmp_path) == []
    with pytest.raises(RuntimeError, match="Ya congelado"):
        forward.freeze(tmp_path, cfg_path)
    (tmp_path / "costs.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "setups.py").unlink()
    assert sorted(forward.changed_rules(cfg, tmp_path)) == ["costs.py", "setups.py"]


def test_closed_after_skips_pre_freeze_and_still_running_trades():
    trades = [
        {"t": 90, "r": 1.0, "outcome": "TP2", "exit_idx": 10},      # antes de congelar
        {"t": 110, "r": -1.0, "outcome": "SL", "exit_idx": 50},     # cuenta
        {"t": 120, "r": 0.2, "outcome": "TIEMPO", "exit_idx": 80},  # cerró por tiempo antes del final: cuenta
        {"t": 130, "r": 0.1, "outcome": "TIEMPO", "exit_idx": 99},  # sigue abierta en la última vela
    ]
    done, still_open = forward.closed_after(trades, freeze_ts=100, last_bar_idx=99)
    assert [t["t"] for t in done] == [110, 120] and still_open == 1


def d1(n, drift):
    closes = 100 * np.cumprod(1 + drift + np.random.default_rng(1).normal(0, 0.004, n))
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame({"time": 1_600_000_000 + np.arange(n) * 86400, "open": opens, "close": closes, "spread": 0})


SPEC = {"point": 0.01, "contract_size": 100.0, "swap_mode": 1, "swap_long": 0.0, "swap_short": 0.0}


def test_tsmom_current_continues_where_completed_trades_stop():
    df = d1(300, 0.002)
    completed = h_b.tsmom_trades(df, "X", SPEC)
    cur = forward.tsmom_current(df, SPEC)
    assert cur["direccion"] == "BUY" and 1 <= cur["sesiones_restantes"] <= 21
    last_entry = datetime.fromtimestamp(completed[-1]["t"], timezone.utc).date().isoformat()
    assert cur["desde"] > last_entry


def test_tsmom_current_none_with_short_history():
    assert forward.tsmom_current(d1(200, 0.001), SPEC) is None
