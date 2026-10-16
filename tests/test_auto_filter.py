import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
import main  # noqa: E402
from main import history_allows_auto, history_for  # noqa: E402


def passing_history(**overrides) -> dict:
    h = {"symbol_n": 120, "symbol_avg_r": 0.2, "symbol_t_stat": 2.5,
         "old_n": 70, "old_avg_r": 0.18, "recent_n": 50, "recent_avg_r": 0.22}
    h.update(overrides)
    return h


# ---------- Filtro del auto-trading ----------

def test_auto_allowed_when_both_halves_and_total_are_significant():
    assert history_allows_auto(passing_history())


@pytest.mark.parametrize("override", [
    {"old_n": 29},                 # tramo antiguo con pocas operaciones
    {"recent_n": 29},              # tramo reciente con pocas operaciones
    {"old_avg_r": 0.049},          # la ventaja no está en el tramo antiguo
    {"recent_avg_r": -0.02},       # la ventaja desaparece en el tramo reciente (caso XAUUSD fuera de muestra)
    {"symbol_t_stat": 1.99},       # media total no distinguible de 0R
    {"symbol_t_stat": None},       # t no calculable
])
def test_auto_blocked_when_any_condition_fails(override):
    assert not history_allows_auto(passing_history(**override))


def test_auto_allowed_exactly_at_thresholds():
    assert history_allows_auto(passing_history(old_n=30, recent_n=30, old_avg_r=0.05, recent_avg_r=0.05,
                                               symbol_t_stat=2.0))


def test_auto_blocked_by_old_rule_pass_that_is_noise():
    """XAUUSD tras retirar el BOS: +0.096R en 48 ops pasaba el filtro anterior; ahora no."""
    assert not history_allows_auto({"symbol_n": 48, "symbol_avg_r": 0.096})


def test_auto_blocked_without_history():
    assert not history_allows_auto(None)
    assert not history_allows_auto({})


# ---------- history_for con y sin tramos ----------

def results_with(nuevo: dict) -> dict:
    return {"symbols": {"XAUUSD": {"period": {"from": "2026-01-01", "to": "2026-10-01"}, "nuevo": nuevo}}}


def test_history_for_exposes_split_and_t_stat(monkeypatch):
    nuevo = {"n": 120, "avg_r": 0.2, "win_rate": 50.0, "profit_factor": 1.4, "t_stat": 2.5, "by_bucket": {},
             "split": {"cutoff": "2026-06-14",
                       "antiguo": {"n": 70, "avg_r": 0.18}, "reciente": {"n": 50, "avg_r": 0.22}}}
    monkeypatch.setattr(main, "backtest_results", results_with(nuevo))
    h = history_for("XAUUSD", 70)
    assert (h["old_n"], h["old_avg_r"], h["recent_n"], h["recent_avg_r"]) == (70, 0.18, 50, 0.22)
    assert h["symbol_t_stat"] == 2.5
    assert history_allows_auto(h)


def test_history_for_old_results_without_split_never_enable_auto(monkeypatch):
    nuevo = {"n": 48, "avg_r": 0.096, "win_rate": 48.0, "profit_factor": 1.2, "by_bucket": {}}
    monkeypatch.setattr(main, "backtest_results", results_with(nuevo))
    h = history_for("XAUUSD", 70)
    assert h["symbol_n"] == 48 and h["old_n"] == 0 and h["symbol_t_stat"] is None
    assert not history_allows_auto(h)


# ---------- Métricas del backtest ----------

def test_t_stat_matches_formula_and_handles_degenerate_cases():
    rs = np.array([1.0, -1.0, 2.0, 0.5])
    expected = rs.mean() / (rs.std(ddof=1) / np.sqrt(len(rs)))
    assert backtest.t_stat(rs) == pytest.approx(expected, abs=0.01)
    assert backtest.t_stat(np.array([1.0])) is None
    assert backtest.t_stat(np.array([0.5, 0.5, 0.5])) is None
    assert backtest.summarize([])["t_stat"] is None


def test_split_by_time_cuts_at_60_percent_of_period():
    trades = [{"t": t, "r": r} for t, r in [(0, 1.0), (59, -1.0), (60, 2.0), (100, 0.5)]]
    split = backtest.split_by_time(trades, first_t=0, last_t=100)
    assert split["antiguo"]["n"] == 2 and split["antiguo"]["total_r"] == pytest.approx(0.0)
    assert split["reciente"]["n"] == 2 and split["reciente"]["total_r"] == pytest.approx(2.5)
    assert split["cutoff"] == "1970-01-01"
