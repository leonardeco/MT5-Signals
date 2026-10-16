"""Métricas de robustez para decidir si un resultado de backtest es ventaja o ruido.

Todo se calcula sobre la lista de resultados por operación en R. Sin scipy: la normal sale de statistics.NormalDist.

- t de la media frente a 0R e intervalo bootstrap de la media.
- Sharpe por operación, Sharpe probabilístico (PSR) y Sharpe deflactado (DSR, Bailey y López de Prado 2014):
  probabilidad de que el Sharpe real supere al máximo que cabría esperar por azar tras `n_trials` intentos.
- Monte Carlo del orden de las operaciones: drawdown máximo en R que se puede esperar con la misma lista.
- Medias por bloques temporales consecutivos (estabilidad en el tiempo).
"""
from __future__ import annotations

import math
from statistics import NormalDist

import numpy as np

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def t_stat(rs) -> float | None:
    rs = np.asarray(rs, dtype=float)
    if len(rs) < 2:
        return None
    sd = float(rs.std(ddof=1))
    return float(rs.mean()) / (sd / math.sqrt(len(rs))) if sd > 0 else None


def bootstrap_mean_ci(rs, n_boot: int = 5000, alpha: float = 0.05, seed: int = 0) -> tuple[float, float] | None:
    rs = np.asarray(rs, dtype=float)
    if len(rs) < 2:
        return None
    rng = np.random.default_rng(seed)
    means = rng.choice(rs, size=(n_boot, len(rs)), replace=True).mean(axis=1)
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def sharpe(rs) -> float | None:
    """Sharpe por operación (sin anualizar): media / desviación."""
    rs = np.asarray(rs, dtype=float)
    if len(rs) < 2:
        return None
    sd = float(rs.std(ddof=1))
    return float(rs.mean()) / sd if sd > 0 else None


def _skew_kurt(rs: np.ndarray) -> tuple[float, float]:
    """Asimetría y curtosis (no en exceso: la normal da 3)."""
    d = rs - rs.mean()
    m2 = float((d ** 2).mean())
    if m2 == 0:
        return 0.0, 3.0
    return float((d ** 3).mean()) / m2 ** 1.5, float((d ** 4).mean()) / m2 ** 2


def probabilistic_sharpe(rs, sr_benchmark: float = 0.0) -> float | None:
    """P(Sharpe real > sr_benchmark) corrigiendo por tamaño de muestra, asimetría y colas gruesas."""
    rs = np.asarray(rs, dtype=float)
    sr = sharpe(rs)
    if sr is None:
        return None
    skew, kurt = _skew_kurt(rs)
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr ** 2
    if denom <= 0:
        return None
    return _N.cdf((sr - sr_benchmark) * math.sqrt(len(rs) - 1) / math.sqrt(denom))


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Sharpe máximo esperado entre n_trials estrategias sin ventaja (Sharpe real 0) con varianza var_sr."""
    if n_trials <= 1 or var_sr <= 0:
        return 0.0
    return math.sqrt(var_sr) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
                                + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e)))


def deflated_sharpe(rs, n_trials: int, var_sr: float | None = None) -> dict | None:
    """Sharpe deflactado. Sin la varianza real de los Sharpe de los intentos se usa la del estimador bajo la
    hipótesis nula, 1/(n-1): es lo que variaría el Sharpe de una estrategia sin ventaja por puro azar."""
    rs = np.asarray(rs, dtype=float)
    sr = sharpe(rs)
    if sr is None:
        return None
    var = var_sr if var_sr is not None else 1.0 / (len(rs) - 1)
    sr0 = expected_max_sharpe(n_trials, var)
    return {"sharpe": sr, "sharpe_azar_max": sr0, "dsr": probabilistic_sharpe(rs, sr0), "n_trials": n_trials}


def max_drawdown(rs) -> float:
    """Mayor caída desde un máximo de la curva acumulada en R (número positivo)."""
    curve = np.concatenate([[0.0], np.cumsum(np.asarray(rs, dtype=float))])
    return float((np.maximum.accumulate(curve) - curve).max())


def monte_carlo_drawdown(rs, n_sims: int = 5000, seed: int = 0) -> dict | None:
    """Barajando el orden de las operaciones: drawdown máximo mediano y al 95 %."""
    rs = np.asarray(rs, dtype=float)
    if len(rs) < 2:
        return None
    rng = np.random.default_rng(seed)
    dds = np.array([max_drawdown(rng.permutation(rs)) for _ in range(n_sims)])
    return {"real": max_drawdown(rs), "p50": float(np.median(dds)), "p95": float(np.quantile(dds, 0.95))}


def block_means(trades: list[dict], n_blocks: int = 5) -> list[dict]:
    """Media R en n bloques consecutivos de igual duración (por la hora 't' de cada operación)."""
    if not trades:
        return []
    ts = np.array([t["t"] for t in trades], dtype=float)
    edges = np.linspace(ts.min(), ts.max(), n_blocks + 1)
    out = []
    for k in range(n_blocks):
        hi_ok = ts <= edges[k + 1] if k == n_blocks - 1 else ts < edges[k + 1]
        rs = [trades[i]["r"] for i in np.flatnonzero((ts >= edges[k]) & hi_ok)]
        out.append({"n": len(rs), "avg_r": round(float(np.mean(rs)), 3) if rs else None})
    return out


def split_halves(trades: list[dict], fraction: float = 0.6) -> tuple[list[dict], list[dict]]:
    """Tramo antiguo (primer `fraction` del periodo) y reciente, por la hora 't' de cada operación."""
    if not trades:
        return [], []
    ts = [t["t"] for t in trades]
    cutoff = min(ts) + fraction * (max(ts) - min(ts))
    return [t for t in trades if t["t"] < cutoff], [t for t in trades if t["t"] >= cutoff]


def _r(x, nd=3):
    return None if x is None else round(float(x), nd)


def report(trades: list[dict], n_trials: int) -> dict:
    """Resumen de robustez de una lista de operaciones con 'r' (ya neto de costes) y 't'."""
    rs = np.array([t["r"] for t in trades], dtype=float)
    old, recent = split_halves(trades)
    ci = bootstrap_mean_ci(rs)
    ds = deflated_sharpe(rs, n_trials)
    mc = monte_carlo_drawdown(rs)
    return {
        "n": int(len(rs)),
        "avg_r": _r(rs.mean()) if len(rs) else None,
        "total_r": _r(rs.sum(), 2) if len(rs) else None,
        "win_rate": _r((rs > 0).mean() * 100, 1) if len(rs) else None,
        "t_stat": _r(t_stat(rs), 2),
        "ic95_media": [_r(ci[0]), _r(ci[1])] if ci else None,
        "sharpe_op": _r(ds["sharpe"]) if ds else None,
        "dsr": _r(ds["dsr"]) if ds and ds["dsr"] is not None else None,
        "sharpe_azar_max": _r(ds["sharpe_azar_max"]) if ds else None,
        "n_trials": n_trials,
        "drawdown_r": {k: _r(v, 2) for k, v in mc.items()} if mc else None,
        "tramo_antiguo": {"n": len(old), "avg_r": _r(np.mean([t["r"] for t in old])) if old else None},
        "tramo_reciente": {"n": len(recent), "avg_r": _r(np.mean([t["r"] for t in recent])) if recent else None},
        "bloques": block_means(trades),
    }


def passes(rep: dict, criterio: dict) -> tuple[bool, list[str]]:
    """Evalúa un informe contra el criterio registrado. Devuelve (pasa, motivos de fallo)."""
    fails = []
    if rep["n"] < criterio.get("n_min", 0):
        fails.append(f"n {rep['n']} < {criterio['n_min']}")
    t = rep["t_stat"]
    if "t_min" in criterio and (t is None or t < criterio["t_min"]):
        fails.append(f"t {t} < {criterio['t_min']}")
    dsr = rep["dsr"]
    if "dsr_min" in criterio and (dsr is None or dsr < criterio["dsr_min"]):
        fails.append(f"DSR {dsr} < {criterio['dsr_min']}")
    if criterio.get("tramos_positivos"):
        for name in ("tramo_antiguo", "tramo_reciente"):
            avg = rep[name]["avg_r"]
            if avg is None or avg <= 0:
                fails.append(f"{name} {avg} ≤ 0")
    return not fails, fails
