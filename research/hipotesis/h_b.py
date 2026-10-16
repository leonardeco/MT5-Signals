"""H-B: momentum de series temporales en D1 (Moskowitz, Ooi y Pedersen 2012). Reglas en registro_hipotesis.json."""
from __future__ import annotations

import json
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from costs import swap_cost_px_per_night

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "US100"]
LOOKBACK, HOLD, VOL_WINDOW = 252, 21, 63


def tsmom_trades(df: pd.DataFrame, symbol: str, spec: dict) -> list[dict]:
    df = df.sort_values("time").reset_index(drop=True)
    o, c, t = df["open"].to_numpy(float), df["close"].to_numpy(float), df["time"].to_numpy(float)
    spr = df["spread"].to_numpy(float) * spec["point"] if "spread" in df else np.zeros(len(df))
    rets = c[1:] / c[:-1] - 1  # rets[i-1] = retorno de la sesión i
    trades = []
    k = LOOKBACK
    while k + 1 + HOLD < len(df):
        e, x = k + 1, k + 1 + HOLD
        signal = c[k] / c[k - LOOKBACK] - 1
        sigma = float(np.std(rets[k - VOL_WINDOW:k], ddof=1))
        if signal != 0 and sigma > 0:
            is_buy = signal > 0
            entry = o[e] + (spr[e] if is_buy else 0.0)
            exit_price = o[x] + (0.0 if is_buy else spr[x])
            nights = (datetime.fromtimestamp(t[x], timezone.utc).date()
                      - datetime.fromtimestamp(t[e], timezone.utc).date()).days
            swap = nights * swap_cost_px_per_night(spec, "BUY" if is_buy else "SELL")
            pnl = ((exit_price - entry) if is_buy else (entry - exit_price)) - swap
            risk = entry * sigma * math.sqrt(HOLD)
            trades.append({"symbol": symbol, "t": float(t[e]), "dir": "BUY" if is_buy else "SELL",
                           "r": pnl / risk, "risk_px": risk, "price": entry, "swap_px": swap})
        k += HOLD
    return trades


def run() -> list[dict]:
    specs = json.loads((CACHE_DIR / "specs.json").read_text(encoding="utf-8"))["simbolos"]
    trades = []
    for sym in SYMBOLS:
        with open(CACHE_DIR / f"rates_{sym}_D1.pkl", "rb") as f:
            v = pickle.load(f)
        trades += tsmom_trades(v["rates"], sym, specs[sym])
    return trades
