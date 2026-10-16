"""Descarga una vez los frames de MT5 que usa el backtest y los guarda en un pickle.

Uso:  python research/cache_frames.py [dias]
"""
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import MetaTrader5 as mt5  # noqa: E402

from backtest import fetch_frames  # noqa: E402
from signal_engine import resolve_symbol  # noqa: E402

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "US100", "USDJPY"]
CACHE_DIR = Path(__file__).with_name("cache")


def cache_path(days: int) -> Path:
    return CACHE_DIR / f"frames_{days}d.pkl"


def main(days: int):
    path = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    if not (mt5.initialize(path=path) if os.path.exists(path) else mt5.initialize()):
        sys.exit(f"No se pudo conectar con MT5: {mt5.last_error()}")
    out = {}
    for sym in SYMBOLS:
        broker = resolve_symbol(sym)
        info = mt5.symbol_info(broker) if broker else None
        if not info:
            print(f"{sym}: no disponible")
            continue
        frames = fetch_frames(broker, days)
        out[sym] = {"broker": broker, "point": info.point, "digits": info.digits, "frames": frames}
        print(sym, broker, {k: len(v) for k, v in frames.items()})
    CACHE_DIR.mkdir(exist_ok=True)
    with open(cache_path(days), "wb") as f:
        pickle.dump(out, f)
    print("guardado", cache_path(days))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 180)
