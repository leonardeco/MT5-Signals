"""Diario de operaciones: resultado en R, excursiones MAE/MFE y comparación vivo vs backtest.

- R de cada pata = beneficio neto (incluye swap y comisión) / dinero que se perdía si saltaba el SL inicial.
- MAE / MFE = peor / mejor excursión del precio durante la operación, en R (velas M1 de MT5).
- Las dos patas de una orden dividida (mismo group_id) forman un plan: su R es la media ponderada por volumen.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import numpy as np


def excursions_r(direction: str, entry: float, sl: float, highs, lows) -> tuple[Optional[float], Optional[float]]:
    """(MAE, MFE) en R, ambos ≥ 0. Necesita al menos una vela y un riesgo > 0."""
    risk = abs(entry - sl)
    if risk <= 0 or len(highs) == 0:
        return None, None
    hi, lo = float(np.max(highs)), float(np.min(lows))
    if direction == "BUY":
        mae, mfe = entry - lo, hi - entry
    else:
        mae, mfe = hi - entry, entry - lo
    return round(max(0.0, mae) / risk, 3), round(max(0.0, mfe) / risk, 3)


def r_from_profit(profit: float, risk_money: Optional[float]) -> Optional[float]:
    if not risk_money or risk_money <= 0:
        return None
    return round(profit / risk_money, 3)


def finalize_closed_trade(trade, deals, mt5) -> None:
    """Rellena r_multiple, mae_r y mfe_r de una pata recién cerrada (no lanza excepciones hacia el escáner)."""
    if not deals or not trade.entry_price or not trade.sl_initial or not trade.volume_initial:
        return
    broker = deals[0].symbol
    is_buy = trade.direction == "BUY"
    try:
        loss = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL, broker,
                                     trade.volume_initial, trade.entry_price, trade.sl_initial)
        trade.r_multiple = r_from_profit(trade.profit or 0.0, abs(loss) if loss else None)
    except Exception as e:
        print(f"[Journal] R de #{trade.ticket}: {e}")
    try:
        start = datetime.fromtimestamp(deals[0].time, timezone.utc)
        end = datetime.fromtimestamp(deals[-1].time, timezone.utc)
        rates = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M1, start, end)
        if rates is not None and len(rates):
            trade.mae_r, trade.mfe_r = excursions_r(trade.direction, trade.entry_price, trade.sl_initial,
                                                    rates["high"], rates["low"])
    except Exception as e:
        print(f"[Journal] MAE/MFE de #{trade.ticket}: {e}")


def plans(trades: list[dict]) -> list[dict]:
    """Agrupa las patas cerradas en planes (una orden única es un plan de una pata)."""
    groups: dict = {}
    for t in trades:
        if t.get("r_multiple") is None:
            continue
        key = t.get("group_id") or f"t{t['ticket']}"
        groups.setdefault(key, []).append(t)
    out = []
    for legs in groups.values():
        vol = sum(t["volume"] or 0 for t in legs) or 1.0
        out.append({
            "symbol": legs[0]["symbol"],
            "r": sum(t["r_multiple"] * (t["volume"] or 0) for t in legs) / vol,
            "mae_r": max((t["mae_r"] for t in legs if t.get("mae_r") is not None), default=None),
            "mfe_r": max((t["mfe_r"] for t in legs if t.get("mfe_r") is not None), default=None),
            "slippage_px": [t["slippage_px"] for t in legs if t.get("slippage_px") is not None],
        })
    return out


def _mean(xs, nd: int = 3):
    xs = [x for x in xs if x is not None]
    return round(float(np.mean(xs)), nd) if xs else None


def journal_stats(trades: list[dict], backtest_by_symbol: dict[str, float]) -> dict:
    """Expectativa en R de los planes cerrados y su comparación con la media neta del backtest por símbolo."""
    ps = plans(trades)
    by_symbol = {}
    for sym in sorted({p["symbol"] for p in ps}):
        sub = [p for p in ps if p["symbol"] == sym]
        by_symbol[sym] = {"n": len(sub), "expectancy_r": _mean([p["r"] for p in sub]),
                          "backtest_avg_r": backtest_by_symbol.get(sym)}
    return {
        "n": len(ps),
        "expectancy_r": _mean([p["r"] for p in ps]),
        "win_rate": round(100 * float(np.mean([p["r"] > 0 for p in ps])), 1) if ps else None,
        "total_r": round(sum(p["r"] for p in ps), 2) if ps else 0.0,
        "avg_mae_r": _mean([p["mae_r"] for p in ps]),
        "avg_mfe_r": _mean([p["mfe_r"] for p in ps]),
        "avg_slippage_px": _mean([s for p in ps for s in p["slippage_px"]], nd=6),
        "by_symbol": by_symbol,
    }
