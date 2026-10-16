import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research import robustness as rb  # noqa: E402


def noise(n=400, mean=0.0, seed=1):
    return np.random.default_rng(seed).normal(mean, 1.0, n)


def test_t_stat_and_sharpe_match_formulas():
    rs = np.array([1.0, -1.0, 2.0, 0.5])
    assert rb.t_stat(rs) == pytest.approx(rs.mean() / (rs.std(ddof=1) / 2))
    assert rb.sharpe(rs) == pytest.approx(rs.mean() / rs.std(ddof=1))
    assert rb.t_stat([1.0]) is None and rb.sharpe([0.3, 0.3]) is None


def test_bootstrap_ci_contains_mean_and_is_reproducible():
    rs = noise(mean=0.1)
    lo, hi = rb.bootstrap_mean_ci(rs)
    assert lo < rs.mean() < hi
    assert rb.bootstrap_mean_ci(rs) == (lo, hi)


def test_psr_is_one_half_when_sharpe_equals_benchmark():
    rs = noise()
    assert rb.probabilistic_sharpe(rs, rb.sharpe(rs)) == pytest.approx(0.5)


def test_expected_max_sharpe_grows_with_trials():
    v = 1 / 400
    assert rb.expected_max_sharpe(1, v) == 0.0
    values = [rb.expected_max_sharpe(n, v) for n in (2, 10, 21, 100)]
    assert values == sorted(values) and values[0] > 0


def test_deflated_sharpe_penalizes_more_trials():
    rs = noise(mean=0.12)
    one, many = rb.deflated_sharpe(rs, 1), rb.deflated_sharpe(rs, 50)
    assert one["dsr"] == pytest.approx(rb.probabilistic_sharpe(rs, 0.0))
    assert many["dsr"] < one["dsr"] and many["sharpe_azar_max"] > 0


def test_pure_noise_does_not_pass_deflated_sharpe_after_21_trials():
    assert rb.deflated_sharpe(noise(mean=0.0, seed=7), 21)["dsr"] < 0.95


def test_max_drawdown_on_known_curve():
    # curva 1, 0, -1, 1, -2 → pico 1, valle -2
    assert rb.max_drawdown([1, -1, -1, 2, -3]) == pytest.approx(3.0)
    assert rb.max_drawdown([0.5, 0.5]) == 0.0


def test_monte_carlo_drawdown_bounds():
    mc = rb.monte_carlo_drawdown(noise(n=200), n_sims=500)
    assert 0 < mc["p50"] <= mc["p95"]
    assert rb.monte_carlo_drawdown([1.0, 2.0, 0.5], n_sims=50)["p95"] == 0.0


def test_block_means_and_split_halves_by_time():
    trades = [{"t": t, "r": r} for t, r in [(0, 1.0), (10, 1.0), (50, -1.0), (90, 2.0), (100, 2.0)]]
    blocks = rb.block_means(trades, n_blocks=2)
    assert blocks == [{"n": 2, "avg_r": 1.0}, {"n": 3, "avg_r": 1.0}]
    old, recent = rb.split_halves(trades)
    assert [t["t"] for t in old] == [0, 10, 50] and [t["t"] for t in recent] == [90, 100]


def test_report_and_criterion():
    rng = np.random.default_rng(3)
    good = [{"t": i, "r": float(r)} for i, r in enumerate(rng.normal(0.4, 1.0, 600))]
    rep = rb.report(good, n_trials=21)
    ok, fails = rb.passes(rep, {"t_min": 2, "dsr_min": 0.95, "tramos_positivos": True, "n_min": 100})
    assert ok and not fails

    flat = [{"t": i, "r": float(r)} for i, r in enumerate(rng.normal(0.0, 1.0, 300))]
    ok, fails = rb.passes(rb.report(flat, n_trials=21), {"t_min": 2, "dsr_min": 0.95})
    assert not ok and any(f.startswith("DSR") for f in fails)
