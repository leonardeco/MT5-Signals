"""Investigación de variantes del plan de entrada con validación temporal (in-sample / out-of-sample).

Hipótesis fijadas ANTES de mirar resultados (una a una, sobre el plan actual):
  H1 sesión      S1 Londres+NY 10:00–19:00 servidor (todos) · S2 por instrumento (US100 16:30–23:00)
  H2 sesgo HTF   B1 H4 (cierre vs EMA50 H4) a favor · B2 D1 (cierre vs EMA20 D1) a favor · B3 ambos
  H3 régimen     R1 ADX M15 ≥ 25 · R2 ADX H1 ≥ 25 · R3 ATR M15 percentil ≥ 50 · R4 percentil 20–80
  H4 score       C1 score ≥ 65 · C2 score ≥ 75
  H5 gatillo     G1 solo envolvente · G2 solo pin bar · G3 solo ruptura (BOS) · G4 sin ruptura
  H6 salida      X1 todo en TP1 · X2 objetivo fijo 1.5R · X3 fijo 2R · X4 parcial sin breakeven
                 X5 sin niveles de liquidez (TP 1.5R/3R, nunca "sin espacio")
Hora del servidor MetaQuotes-Demo = UTC+2/+3 (apertura contado US100 a las 16:30 servidor).

Validación: corte temporal común al 60% del periodo; criterio para pasar (también fijado antes):
  a) media R fuera de muestra (OOS) mejor que la base en ≥ 3 de 5 pares,
  b) media R OOS agregada ≥ +0.05R con n ≥ 30, y c) media R in-sample agregada > 0.

Nota: desde que se retiró el gatillo de ruptura (BOS) de setups.m5_trigger, BASE equivale a G4 y G3 da 0 operaciones;
los resultados guardados en variants_340d.json son del motor anterior (ver INFORME_VARIANTES.md).

Uso:  python research/explore_variants.py [dias_cache]
"""
import json
import pickle
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backtest  # noqa: E402
from backtest import backtest_frames, simulate_trade, summarize  # noqa: E402
from signal_engine import QuantSignalEngine  # noqa: E402

HERE = Path(__file__).parent
IS_FRACTION = 0.6


# ---------------------------------------------------------------------------
# Rasgos por vela M15 (índice i igual al del bucle de backtest_frames)
# ---------------------------------------------------------------------------

def _last_closed(close_t: np.ndarray, T: np.ndarray) -> np.ndarray:
    return np.searchsorted(close_t, T, side="right") - 1


def features(frames: dict) -> SimpleNamespace:
    m15 = QuantSignalEngine._compute_indicators(frames["m15"].copy())
    h1 = QuantSignalEngine._compute_indicators(frames["h1"].copy())
    T = m15["time"].to_numpy(float) + 900
    hm = pd.to_datetime(T, unit="s")
    out = pd.DataFrame({"T": T, "hour": hm.hour + hm.minute / 60.0, "adx15": m15["adx"].to_numpy(float)})

    hidx = _last_closed(h1["time"].to_numpy(float) + 3600, T)
    out["adx_h1"] = np.where(hidx >= 0, h1["adx"].to_numpy(float)[np.clip(hidx, 0, None)], np.nan)

    # H4 a partir de H1 (bloques de 4 h en hora del servidor)
    h1t = frames["h1"]["time"].to_numpy(float)
    grp = (h1t // 14400).astype(np.int64)
    h4 = pd.DataFrame({"g": grp, "close": frames["h1"]["close"].to_numpy(float)}).groupby("g")["close"].last()
    h4_close_t = h4.index.to_numpy(float) * 14400 + 14400
    h4_ema = h4.ewm(span=50, adjust=False).mean().to_numpy()
    k = _last_closed(h4_close_t, T)
    out["h4_bias"] = np.where(k >= 0, np.sign(h4.to_numpy()[np.clip(k, 0, None)] - h4_ema[np.clip(k, 0, None)]), 0)

    d1 = frames["d1"]
    d1c = d1["close"].astype(float)
    d1_ema = d1c.ewm(span=20, adjust=False).mean().to_numpy()
    k = _last_closed(d1["time"].to_numpy(float) + 86400, T)
    out["d1_bias"] = np.where(k >= 20, np.sign(d1c.to_numpy()[np.clip(k, 0, None)] - d1_ema[np.clip(k, 0, None)]), 0)

    atr = m15["atr"]
    out["atr_pct"] = atr.rolling(1920, min_periods=480).rank(pct=True).to_numpy()
    return SimpleNamespace(**{c: out[c].to_numpy() for c in out.columns})


# ---------------------------------------------------------------------------
# Variantes
# ---------------------------------------------------------------------------

def sess_all(f, i, d, s):
    return 10.0 <= f.hour[i] <= 19.0


def sess_by_symbol(sym):
    if sym == "US100":
        return lambda f, i, d, s: 16.5 <= f.hour[i] <= 23.0
    return sess_all


def bias(col):
    return lambda f, i, d, s: getattr(f, col)[i] == (1 if d == "BUY" else -1)


def both_bias(f, i, d, s):
    want = 1 if d == "BUY" else -1
    return f.h4_bias[i] == want and f.d1_bias[i] == want


def fixed_rr(rr):
    def fn(direction, entry, plan, m5, start):
        risk = abs(entry - plan.sl)
        tp = entry + rr * risk if direction == "BUY" else entry - rr * risk
        return simulate_trade(direction, entry, plan.sl, tp, tp, m5, start, partial=False)
    return fn


def tp1_only(direction, entry, plan, m5, start):
    return simulate_trade(direction, entry, plan.sl, plan.tp1, plan.tp1, m5, start, partial=False)


def partial_no_be(direction, entry, plan, m5, start):
    """50% en TP1 y el resto con el stop original hasta TP2."""
    is_buy = direction == "BUY"
    risk = abs(entry - plan.sl)
    if risk <= 0:
        return {"r": 0.0, "outcome": "ERROR", "exit_idx": start}
    n = len(m5["close"])
    end = min(n, start + backtest.MAX_HOLD_M5)
    r_at = lambda p: ((p - entry) if is_buy else (entry - p)) / risk  # noqa: E731
    banked, half = 0.0, False
    for j in range(start, end):
        spr = m5["spread_px"][j]
        worst, best = (m5["low"][j], m5["high"][j]) if is_buy else (m5["high"][j] + spr, m5["low"][j] + spr)
        hit_stop = worst <= plan.sl if is_buy else worst >= plan.sl
        hit = (lambda t: best >= t) if is_buy else (lambda t: best <= t)
        if hit_stop:
            return {"r": (banked - 0.5) if half else -1.0, "outcome": "SL", "exit_idx": j}
        if not half and hit(plan.tp1):
            banked, half = 0.5 * r_at(plan.tp1), True
        if half and hit(plan.tp2):
            return {"r": banked + 0.5 * r_at(plan.tp2), "outcome": "TP2", "exit_idx": j}
    last = end - 1
    px = m5["close"][last] + (0 if is_buy else m5["spread_px"][last])
    return {"r": (banked + 0.5 * r_at(px)) if half else r_at(px), "outcome": "TIEMPO", "exit_idx": last}


@contextmanager
def no_levels():
    orig = backtest.collect_levels
    backtest.collect_levels = lambda *a, **k: []
    try:
        yield
    finally:
        backtest.collect_levels = orig


@contextmanager
def nothing():
    yield


def trig_is(*names):
    return lambda t: any(n in t for n in names)


# nombre → (hipótesis, setup_filter(f, i, d, s) | fábrica por símbolo, trigger_filter, exit_fn, contexto)
VARIANTS = {
    "BASE": ("Base", None, None, None, nothing),
    "S1 Londres+NY": ("H1 sesión", sess_all, None, None, nothing),
    "S2 sesión por instrumento": ("H1 sesión", "by_symbol", None, None, nothing),
    "B1 sesgo H4": ("H2 sesgo", bias("h4_bias"), None, None, nothing),
    "B2 sesgo D1": ("H2 sesgo", bias("d1_bias"), None, None, nothing),
    "B3 sesgo H4+D1": ("H2 sesgo", both_bias, None, None, nothing),
    "R1 ADX M15>=25": ("H3 régimen", lambda f, i, d, s: f.adx15[i] >= 25, None, None, nothing),
    "R2 ADX H1>=25": ("H3 régimen", lambda f, i, d, s: f.adx_h1[i] >= 25, None, None, nothing),
    "R3 ATR pct>=50": ("H3 régimen", lambda f, i, d, s: f.atr_pct[i] >= 0.5, None, None, nothing),
    "R4 ATR pct 20-80": ("H3 régimen", lambda f, i, d, s: 0.2 <= f.atr_pct[i] <= 0.8, None, None, nothing),
    "C1 score>=65": ("H4 score", lambda f, i, d, s: s >= 65, None, None, nothing),
    "C2 score>=75": ("H4 score", lambda f, i, d, s: s >= 75, None, None, nothing),
    "G1 solo envolvente": ("H5 gatillo", None, trig_is("Envolvente"), None, nothing),
    "G2 solo pin bar": ("H5 gatillo", None, trig_is("Pin bar"), None, nothing),
    "G3 solo ruptura": ("H5 gatillo", None, trig_is("Ruptura"), None, nothing),
    "G4 sin ruptura": ("H5 gatillo", None, trig_is("Envolvente", "Pin bar"), None, nothing),
    "X1 todo en TP1": ("H6 salida", None, None, tp1_only, nothing),
    "X2 fijo 1.5R": ("H6 salida", None, None, fixed_rr(1.5), nothing),
    "X3 fijo 2R": ("H6 salida", None, None, fixed_rr(2.0), nothing),
    "X4 parcial sin BE": ("H6 salida", None, None, partial_no_be, nothing),
    "X5 sin niveles (1.5R/3R)": ("H6 salida", None, None, None, no_levels),
}


def run_variant(data: dict, feats: dict, name: str, spec=None) -> dict[str, list[dict]]:
    _, sf, tf, ef, ctx = spec or VARIANTS[name]
    out = {}
    for sym, v in data.items():
        f = feats[sym]
        fn = sess_by_symbol(sym) if sf == "by_symbol" else sf
        setup_filter = (lambda i, d, s, fn=fn, f=f: bool(fn(f, i, d, s))) if fn else None
        with ctx():
            res = backtest_frames(v["frames"], v["point"], v["digits"], setup_filter=setup_filter,
                                  trigger_filter=tf, exit_fn=ef)
        out[sym] = res["trades_nuevo"]
    return out


def split(trades: list[dict], cutoff: float) -> tuple[list, list]:
    return [t for t in trades if t["t"] < cutoff], [t for t in trades if t["t"] >= cutoff]


def common_cutoff(data: dict) -> float:
    start = max(float(v["frames"]["m5"]["time"].iloc[0]) for v in data.values())
    end = min(float(v["frames"]["m5"]["time"].iloc[-1]) for v in data.values())
    return start + IS_FRACTION * (end - start)


def evaluate(trades_by_sym: dict, cutoff: float) -> dict:
    rows = {}
    all_is, all_oos = [], []
    for sym, tr in trades_by_sym.items():
        a, b = split(tr, cutoff)
        rows[sym] = {"is": summarize(a), "oos": summarize(b)}
        all_is += a
        all_oos += b
    rows["TOTAL"] = {"is": summarize(all_is), "oos": summarize(all_oos)}
    return rows


def verdict(ev: dict, base: dict) -> dict:
    syms = [s for s in ev if s != "TOTAL"]
    better = sum(1 for s in syms if ev[s]["oos"]["n"] > 0 and ev[s]["oos"]["avg_r"] > base[s]["oos"]["avg_r"])
    tot = ev["TOTAL"]
    ok = better >= 3 and tot["oos"]["n"] >= 30 and tot["oos"]["avg_r"] >= 0.05 and tot["is"]["avg_r"] > 0
    return {"pairs_better_oos": better, "passes": bool(ok)}


def load(days: int) -> dict:
    with open(HERE / "cache" / f"frames_{days}d.pkl", "rb") as fh:
        return pickle.load(fh)


def main(days: int):
    data = load(days)
    feats = {s: features(v["frames"]) for s, v in data.items()}
    cutoff = common_cutoff(data)
    print("corte IS/OOS:", pd.to_datetime(cutoff, unit="s"))
    report = {"cutoff": cutoff, "variants": {}}
    base = None
    for name, spec in VARIANTS.items():
        trades = run_variant(data, feats, name)
        ev = evaluate(trades, cutoff)
        if base is None:
            base = ev
        ver = verdict(ev, base)
        report["variants"][name] = {"hypothesis": spec[0], "eval": ev, **ver}
        t = ev["TOTAL"]
        print(f"{name:28s} IS n={t['is']['n']:4d} {t['is']['avg_r']:+.3f}R PF={t['is']['profit_factor']}"
              f" | OOS n={t['oos']['n']:4d} {t['oos']['avg_r']:+.3f}R PF={t['oos']['profit_factor']}"
              f" | mejora OOS {ver['pairs_better_oos']}/5 {'PASA' if ver['passes'] else ''}")
    (HERE / f"variants_{days}d.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 340)
