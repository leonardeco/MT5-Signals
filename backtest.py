"""Backtest del motor de señales sobre el historial de MT5.

Compara, sobre las mismas señales, el método anterior (entrada a mercado, SL 1.5 ATR / TP 3 ATR)
con el plan nuevo (zona + gatillo M5 + SL/TP por estructura, 50% en TP1 y resto a breakeven).
Usa exactamente score_bar, build_plan, m5_trigger y SetupTracker del escáner en vivo.

Uso:  python backtest.py [dias]
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from setups import (
    SetupTracker, build_plan, collect_levels, m5_trigger, recent_fvg,
    ACTIVADA, DESCARTADA, EXPIRADA, INVALIDADA,
)
from costs import apply_costs, extra_cost_px
from signal_engine import QuantSignalEngine, score_bar

RESULTS_PATH = Path(__file__).with_name("backtest_results.json")
DEFAULT_DAYS = 180
MAX_HOLD_M5 = 96          # cierre por tiempo a las 8 horas
FVG_BONUS = 10            # mismo bono que suma el copilot en vivo
WARMUP_M15 = 300
WARMUP_H1 = 250
SCORE_BUCKETS = [("55-64", 55, 64), ("65-74", 65, 74), ("75+", 75, 100)]
SPLIT_FRACTION = 0.6      # tramo antiguo = primer 60% del periodo; reciente = 40% restante


def score_bucket(score: int) -> str:
    for name, lo, hi in SCORE_BUCKETS:
        if lo <= score <= hi:
            return name
    return "<55"


# ---------------------------------------------------------------------------
# Simulación de una operación sobre velas M5 (precios bid; el ask = bid + spread)
# ---------------------------------------------------------------------------

def simulate_trade(direction: str, entry: float, sl: float, tp1: float, tp2: float, m5: dict,
                   start: int, partial: bool) -> dict:
    """partial=True: 50% en TP1, stop a breakeven, resto a TP2. partial=False: todo a tp1.
    Si en la misma vela se tocan SL y objetivo, se asume el SL (conservador)."""
    is_buy = direction == "BUY"
    risk = abs(entry - sl)
    if risk <= 0:
        return {"r": 0.0, "outcome": "ERROR", "exit_idx": start}
    n = len(m5["close"])
    end = min(n, start + MAX_HOLD_M5)
    banked, half_done, stop = 0.0, False, sl

    def r_at(price):
        return ((price - entry) if is_buy else (entry - price)) / risk

    for j in range(start, end):
        spr = m5["spread_px"][j]
        if is_buy:
            worst, best = m5["low"][j], m5["high"][j]
            hit_stop = worst <= stop
            hit = lambda target: best >= target  # noqa: E731
        else:
            worst, best = m5["high"][j] + spr, m5["low"][j] + spr
            hit_stop = worst >= stop
            hit = lambda target: best <= target  # noqa: E731

        if not half_done:
            if hit_stop:
                return {"r": -1.0, "outcome": "SL", "exit_idx": j}
            if hit(tp1):
                if not partial:
                    return {"r": r_at(tp1), "outcome": "TP", "exit_idx": j}
                banked, half_done, stop = 0.5 * r_at(tp1), True, entry
                if hit(tp2):
                    return {"r": banked + 0.5 * r_at(tp2), "outcome": "TP2", "exit_idx": j}
        else:
            if hit_stop:
                return {"r": banked, "outcome": "TP1+BE", "exit_idx": j}
            if hit(tp2):
                return {"r": banked + 0.5 * r_at(tp2), "outcome": "TP2", "exit_idx": j}

    last = end - 1
    exit_price = m5["close"][last] + (0 if is_buy else m5["spread_px"][last])
    r = (banked + 0.5 * r_at(exit_price)) if half_done else r_at(exit_price)
    return {"r": r, "outcome": "TIEMPO", "exit_idx": last}


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------

def summarize(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "win_rate": 0.0, "avg_r": 0.0, "total_r": 0.0, "profit_factor": 0.0, "max_losing_streak": 0,
                "t_stat": None}
    rs = np.array([t["r"] for t in trades])
    gains, losses = rs[rs > 0].sum(), -rs[rs < 0].sum()
    streak = worst = 0
    for r in rs:
        streak = streak + 1 if r < 0 else 0
        worst = max(worst, streak)
    return {
        "n": int(len(rs)),
        "win_rate": round(float((rs > 0).mean() * 100), 1),
        "avg_r": round(float(rs.mean()), 3),
        "total_r": round(float(rs.sum()), 2),
        "profit_factor": round(float(gains / losses), 2) if losses > 0 else None,
        "max_losing_streak": int(worst),
        "t_stat": t_stat(rs),
    }


def t_stat(rs: np.ndarray) -> float | None:
    """t de la media frente a 0R: media / (desviación muestral / raíz de n). None si no es calculable."""
    if len(rs) < 2:
        return None
    sd = float(rs.std(ddof=1))
    return round(float(rs.mean()) / (sd / np.sqrt(len(rs))), 2) if sd > 0 else None


def split_by_time(trades: list[dict], first_t: float, last_t: float) -> dict:
    """Métricas del tramo antiguo (primer 60% del periodo) y del reciente (40% restante) por hora de la señal."""
    cutoff = first_t + SPLIT_FRACTION * (last_t - first_t)
    return {
        "cutoff": datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%d"),
        "antiguo": summarize([t for t in trades if t["t"] < cutoff]),
        "reciente": summarize([t for t in trades if t["t"] >= cutoff]),
    }


def summarize_with_buckets(trades: list[dict]) -> dict:
    out = summarize(trades)
    out["by_bucket"] = {name: summarize([t for t in trades if t["bucket"] == name]) for name, _, _ in SCORE_BUCKETS}
    return out


# ---------------------------------------------------------------------------
# Backtest de un símbolo a partir de DataFrames con el formato de copy_rates (time en epoch)
# ---------------------------------------------------------------------------

def _arrays(df: pd.DataFrame, point: float, seconds: int) -> dict:
    return {
        "time": df["time"].to_numpy(dtype=float),
        "close_t": df["time"].to_numpy(dtype=float) + seconds,
        "open": df["open"].to_numpy(dtype=float),
        "high": df["high"].to_numpy(dtype=float),
        "low": df["low"].to_numpy(dtype=float),
        "close": df["close"].to_numpy(dtype=float),
        "spread_px": df["spread"].to_numpy(dtype=float) * point if "spread" in df else np.zeros(len(df)),
    }


def backtest_frames(frames: dict, point: float, digits: int, setup_filter=None, trigger_filter=None,
                    exit_fn=None, cost_px: float = 0.0) -> dict:
    """cost_px: coste extra por operación en unidades de precio (costs.extra_cost_px); se descuenta en R.

    Ganchos opcionales para investigar variantes sin duplicar el bucle:
    setup_filter(i, direction, score) -> bool   descarta setups (i = índice de la vela M15 de señal)
    trigger_filter(trigger) -> bool             ignora gatillos de cierto tipo
    exit_fn(direction, entry, plan, m5, start) -> dict   reemplaza la gestión de la operación
    """
    m15_df = QuantSignalEngine._compute_indicators(frames["m15"].copy())
    h1_df = QuantSignalEngine._compute_indicators(frames["h1"].copy())
    m15, h1, m5 = _arrays(m15_df, point, 900), _arrays(h1_df, point, 3600), _arrays(frames["m5"], point, 300)
    d1 = _arrays(frames["d1"], point, 86400) if frames.get("d1") is not None else None
    w1 = _arrays(frames["w1"], point, 7 * 86400) if frames.get("w1") is not None else None
    rows15 = m15_df.to_dict("records")
    rows_h1 = h1_df.to_dict("records")

    trades_new, trades_old = [], []
    funnel = {"setups": 0, "activadas": 0, "expiradas": 0, "invalidadas": 0, "sin_espacio": 0}
    busy_new = busy_old = -np.inf
    n15, n5 = len(rows15), len(m5["close"])

    for i in range(WARMUP_M15, n15 - 1):
        T = m15["close_t"][i]
        if T <= m5["close_t"][0] + 3 * 300:
            continue
        hidx = int(np.searchsorted(h1["close_t"], T, side="right")) - 1
        if hidx < WARMUP_H1:
            continue
        row = rows15[i]
        atr = float(row["atr"])
        if not atr > 0:
            continue
        sc = score_bar(row, rows15[i - 1], rows_h1[hidx], m15["spread_px"][i], atr, digits)
        direction = sc["direction"]
        if direction == "NEUTRAL":
            continue
        is_buy = direction == "BUY"
        o, h, lo, c = m15["open"], m15["high"], m15["low"], m15["close"]
        fvg_now = (lo[i] > h[i - 2] and c[i - 1] > o[i - 1]) if is_buy else (h[i] < lo[i - 2] and c[i - 1] < o[i - 1])
        score = min(100, sc["score"] + (FVG_BONUS if fvg_now else 0))
        bucket = score_bucket(score)
        j0 = int(np.searchsorted(m5["close_t"], T, side="right"))
        if j0 >= n5:
            break
        spr = m15["spread_px"][i]
        price0 = c[i] + (spr if is_buy else 0.0)

        # --- Método anterior: a mercado al cierre de la vela M15, SL 1.5 ATR / TP 3 ATR
        if T >= busy_old:
            sl_old = price0 - 1.5 * atr if is_buy else price0 + 1.5 * atr
            tp_old = price0 + 3.0 * atr if is_buy else price0 - 3.0 * atr
            res = simulate_trade(direction, price0, sl_old, tp_old, tp_old, m5, j0, partial=False)
            busy_old = m5["close_t"][res["exit_idx"]]
            trades_old.append({"t": T, "dir": direction, "score": score, "bucket": bucket,
                               "risk_px": 1.5 * atr, **res})

        # --- Plan nuevo: setup con zona, gatillo M5 y objetivos de liquidez
        if T < busy_new:
            continue
        if setup_filter is not None and not setup_filter(i, direction, score):
            continue
        funnel["setups"] += 1
        prev_day = prev_week = None
        if d1 is not None:
            di = int(np.searchsorted(d1["close_t"], T, side="right")) - 1
            if di >= 0:
                prev_day = (d1["high"][di], d1["low"][di])
        if w1 is not None:
            wi = int(np.searchsorted(w1["close_t"], T, side="right")) - 1
            if wi >= 0:
                prev_week = (w1["high"][wi], w1["low"][wi])
        levels = collect_levels(h[max(0, i - 95):i + 1], lo[max(0, i - 95):i + 1],
                                h1["high"][max(0, hidx - 119):hidx + 1], h1["low"][max(0, hidx - 119):hidx + 1],
                                prev_day, prev_week)
        fvg = recent_fvg(o[:i + 1], h[:i + 1], lo[:i + 1], c[:i + 1], direction)
        ema21 = float(row["ema21"])
        recent_lows, recent_highs = lo[i - 5:i + 1], h[i - 5:i + 1]

        def plan_at(price):
            return build_plan(direction, ema21, atr, recent_lows, recent_highs, fvg, levels, price, digits)

        tracker = SetupTracker()
        tracker.update("bt", plan_at(price0), price0, T, signal_bar_close=T, origin_score=score)
        last_state = None
        j = j0
        while j < n5:
            ct = m5["close_t"][j]
            price = m5["close"][j] + (m5["spread_px"][j] if is_buy else 0.0)
            plan = plan_at(price)
            trig = m5_trigger(m5["open"][j - 3:j + 1], m5["high"][j - 3:j + 1],
                              m5["low"][j - 3:j + 1], m5["close"][j - 3:j + 1], plan)
            if trig and trigger_filter is not None and not trigger_filter(trig):
                trig = None
            st = tracker.update("bt", plan, price, ct, trigger=trig, trigger_bar_close=ct)
            if st["state"] == ACTIVADA:
                funnel["activadas"] += 1
                if exit_fn is None:
                    res = simulate_trade(direction, price, plan.sl, plan.tp1, plan.tp2, m5, j + 1, partial=True)
                else:
                    res = exit_fn(direction, price, plan, m5, j + 1)
                busy_new = m5["close_t"][min(res["exit_idx"], n5 - 1)]
                trades_new.append({"t": T, "i": i, "dir": direction, "score": score, "bucket": bucket,
                                   "trigger": trig, "rr_tp1": plan.rr_tp1, "rr_tp2": plan.rr_tp2,
                                   "risk_px": abs(price - plan.sl), **res})
                break
            if st["state"] == INVALIDADA:
                funnel["invalidadas"] += 1
                busy_new = ct
                break
            if st["state"] == EXPIRADA:
                funnel["sin_espacio" if last_state == DESCARTADA else "expiradas"] += 1
                busy_new = ct
                break
            last_state = st["state"]
            j += 1

    if cost_px:
        trades_new, trades_old = apply_costs(trades_new, cost_px), apply_costs(trades_old, cost_px)
    first_t, last_t = m5["time"][0], m5["time"][-1]
    return {
        "period": {
            "from": datetime.fromtimestamp(first_t, timezone.utc).strftime("%Y-%m-%d"),
            "to": datetime.fromtimestamp(last_t, timezone.utc).strftime("%Y-%m-%d"),
        },
        "nuevo": {**summarize_with_buckets(trades_new), "funnel": funnel,
                  "split": split_by_time(trades_new, first_t, last_t)},
        "trades_nuevo": trades_new,
        "anterior": summarize_with_buckets(trades_old),
        "costes": {
            "extra_px": cost_px,
            "medio_r_nuevo": round(float(np.mean([t["coste_r"] for t in trades_new])), 3) if cost_px and trades_new else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Datos de MT5 y ejecución completa
# ---------------------------------------------------------------------------

def fetch_frames(broker_symbol: str, days: int) -> dict:
    import MetaTrader5 as mt5
    counts = {
        "m5": (mt5.TIMEFRAME_M5, days * 288),
        "m15": (mt5.TIMEFRAME_M15, days * 96 + WARMUP_M15 + 800),
        "h1": (mt5.TIMEFRAME_H1, days * 24 + WARMUP_H1 + 800),
        "d1": (mt5.TIMEFRAME_D1, days + 10),
        "w1": (mt5.TIMEFRAME_W1, days // 7 + 5),
    }
    frames = {}
    for key, (tf, count) in counts.items():
        rates = None
        for _ in range(3):  # la primera petición puede disparar la descarga del historial
            rates = mt5.copy_rates_from_pos(broker_symbol, tf, 1, count)  # desde 1: solo velas cerradas
            if rates is not None and len(rates) > 0:
                break
            time.sleep(1.0)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"Sin historial {key} para {broker_symbol}: {mt5.last_error()}")
        frames[key] = pd.DataFrame(rates)
    return frames


def run_backtest(symbols: list[str], days: int = DEFAULT_DAYS) -> dict:
    import MetaTrader5 as mt5
    from signal_engine import resolve_symbol

    results = {"generated_at": datetime.now().isoformat(timespec="seconds"), "days": days, "symbols": {}}
    for sym in symbols:
        broker = resolve_symbol(sym)
        info = mt5.symbol_info(broker) if broker else None
        if not info:
            results["symbols"][sym] = {"error": "Símbolo no disponible en el broker"}
            continue
        try:
            started = time.time()
            frames = fetch_frames(broker, days)
            cost = extra_cost_px(sym, price=float(frames["m5"]["close"].iloc[-1]))
            res = backtest_frames(frames, info.point, info.digits, cost_px=cost)
            res.pop("trades_nuevo", None)
            res["broker_symbol"] = broker
            res["seconds"] = round(time.time() - started, 1)
            results["symbols"][sym] = res
        except Exception as e:
            results["symbols"][sym] = {"error": str(e)}
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results


def load_results() -> dict | None:
    try:
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    import MetaTrader5 as mt5

    sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows (cp1252) no imprime "→"

    days = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DAYS
    path = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    if not (mt5.initialize(path=path) if os.path.exists(path) else mt5.initialize()):
        sys.exit(f"No se pudo conectar con MT5: {mt5.last_error()}")
    out = run_backtest(["XAUUSD", "EURUSD", "GBPUSD", "US100", "USDJPY"], days)
    for sym, r in out["symbols"].items():
        if "error" in r:
            print(f"{sym}: ERROR {r['error']}")
            continue
        nv, an = r["nuevo"], r["anterior"]
        print(f"\n{sym} ({r['broker_symbol']}) {r['period']['from']} → {r['period']['to']}  [{r['seconds']}s]")
        print(f"  Anterior: n={an['n']:4d}  acierto={an['win_rate']:5.1f}%  media={an['avg_r']:+.3f}R  total={an['total_r']:+.1f}R  PF={an['profit_factor']}")
        print(f"  Nuevo   : n={nv['n']:4d}  acierto={nv['win_rate']:5.1f}%  media={nv['avg_r']:+.3f}R  total={nv['total_r']:+.1f}R  PF={nv['profit_factor']}")
        print(f"  Embudo  : {nv['funnel']}  t={nv['t_stat']}  coste extra {r['costes']['extra_px']} px "
              f"(≈{r['costes']['medio_r_nuevo']}R por operación)")
        for tramo, st in nv["split"].items():
            if tramo != "cutoff":
                print(f"    {tramo:8s} (corte {nv['split']['cutoff']}): n={st['n']:3d}  media={st['avg_r']:+.3f}R")
        for b, st in nv["by_bucket"].items():
            print(f"    score {b:6s}: n={st['n']:3d}  acierto={st['win_rate']:5.1f}%  media={st['avg_r']:+.3f}R")
