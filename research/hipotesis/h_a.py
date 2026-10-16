"""H-A: momentum intradía en US100 (Gao, Han, Li y Zhou 2018). Reglas exactas en research/registro_hipotesis.json.

Velas M15 en hora del servidor (la vela de las 16:30 es la apertura de contado; la de las 22:45 termina al cierre).
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path(__file__).resolve().parents[1] / "cache" / "rates_US100_M15.pkl"
ATR_STOP_MULT = 2.0


def wilder_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def trades_from_m15(df: pd.DataFrame, point: float, symbol: str = "US100") -> list[dict]:
    df = df.sort_values("time").reset_index(drop=True).copy()
    df["atr"] = wilder_atr(df)
    ts = pd.to_datetime(df["time"], unit="s")
    df["date"], df["hm"] = ts.dt.date, ts.dt.strftime("%H:%M")
    spread = (df["spread"] * point) if "spread" in df else pd.Series(0.0, index=df.index)
    df["spr"] = spread.to_numpy()
    by_day = {d: g.set_index("hm") for d, g in df.groupby("date")}

    trades, prev_close = [], None
    for d in sorted(by_day):
        g = by_day[d]
        need = ("16:45", "22:15", "22:30", "22:45")
        if not all(h in g.index for h in need):
            prev_close = None  # el día anterior de referencia tiene que estar completo
            continue
        close_ref, today_close = prev_close, float(g.loc["22:45", "close"])
        prev_close = today_close
        if close_ref is None:
            continue
        r1 = float(g.loc["16:45", "close"]) / close_ref - 1
        if r1 == 0:
            continue
        is_buy = r1 > 0
        bar_in, bar_out = g.loc["22:30"], g.loc["22:45"]
        risk = ATR_STOP_MULT * float(g.loc["22:15", "atr"])
        if not risk > 0:
            continue
        entry = float(bar_in["open"]) + (float(bar_in["spr"]) if is_buy else 0.0)
        stop = entry - risk if is_buy else entry + risk
        exit_price = None
        for bar in (bar_in, bar_out):
            hit = bar["low"] <= stop if is_buy else bar["high"] + bar["spr"] >= stop
            if hit:
                exit_price = stop
                break
        if exit_price is None:
            exit_price = float(bar_out["close"]) + (0.0 if is_buy else float(bar_out["spr"]))
        pnl = (exit_price - entry) if is_buy else (entry - exit_price)
        trades.append({"symbol": symbol, "t": float(bar_in["time"]), "dir": "BUY" if is_buy else "SELL",
                       "r": pnl / risk, "risk_px": risk, "price": entry, "r1": r1})
    return trades


def run() -> list[dict]:
    with open(CACHE, "rb") as f:
        v = pickle.load(f)
    return trades_from_m15(v["rates"], v["point"])
