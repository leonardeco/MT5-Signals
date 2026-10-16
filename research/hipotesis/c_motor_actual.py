"""Control C-MOTOR-ACTUAL: el motor de señales tal como está en vivo (sin gatillo BOS), sobre la caché de 340 días.

No es una hipótesis nueva (no suma intentos): sirve para medir el motor actual con costes reales y comprobar que
el laboratorio reproduce el informe de variantes (G4 ≈ +0.02R bruto).
"""
import pickle
from pathlib import Path

import backtest

CACHE = Path(__file__).resolve().parents[1] / "cache" / "frames_340d.pkl"


def run() -> list[dict]:
    with open(CACHE, "rb") as f:
        data = pickle.load(f)
    trades = []
    for sym, v in data.items():
        res = backtest.backtest_frames(v["frames"], v["point"], v["digits"])
        close = v["frames"]["m5"]["close"].to_numpy()
        for t in res["trades_nuevo"]:
            trades.append({"symbol": sym, "t": t["t"], "r": t["r"], "risk_px": t["risk_px"],
                           "price": float(close[min(t["exit_idx"], len(close) - 1)])})
    return trades
