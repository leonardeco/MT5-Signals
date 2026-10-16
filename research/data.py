"""Historial largo y spreads reales desde MT5, con caché local (solo lectura: no envía órdenes).

MetaQuotes-Demo (medido el 15-oct-2026): D1 desde 2000 (FX) / 2004 (XAUUSD). El terminal limita cada petición a
`maxbars` (100 000): un rango con más velas da "Invalid params", así que se prueba desde 2000 y se adelanta el inicio.

Uso:
    python -m research.data rates D1 H1        # descarga/actualiza el historial de los 5 símbolos
    python -m research.data spreads 3          # mide el spread real de los ticks de los últimos N días
    python -m research.data specs              # guarda especificaciones y swaps actuales (cache/specs.json)
"""
from __future__ import annotations

import json
import os
import pickle
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "US100", "USDJPY"]
CACHE_DIR = Path(__file__).with_name("cache")
SPREADS_PATH = CACHE_DIR / "spreads.json"
TF_NAMES = ("M5", "M15", "H1", "H4", "D1", "W1")
START_YEARS = (2000, 2005, 2010, 2014, 2017, 2019, 2021, 2023, 2024, 2025)


def connect():
    import MetaTrader5 as mt5
    path = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
    if not (mt5.initialize(path=path) if os.path.exists(path) else mt5.initialize()):
        raise RuntimeError(f"No se pudo conectar con MT5: {mt5.last_error()}")
    return mt5


def rates_path(symbol: str, tf: str) -> Path:
    return CACHE_DIR / f"rates_{symbol}_{tf}.pkl"


def load_rates(symbol: str, tf: str) -> pd.DataFrame | None:
    """Historial en caché (columnas de copy_rates: time en epoch del servidor, open, high, low, close, ...)."""
    try:
        with open(rates_path(symbol, tf), "rb") as f:
            return pickle.load(f)["rates"]
    except (OSError, pickle.UnpicklingError, KeyError):
        return None


def merge_rates(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Une caché y descarga nueva sin duplicar velas (la nueva gana si coincide la hora)."""
    if old is None or old.empty:
        return new.sort_values("time").reset_index(drop=True)
    both = pd.concat([old, new]).drop_duplicates("time", keep="last")
    return both.sort_values("time").reset_index(drop=True)


def download_rates(mt5, symbol: str, tf: str) -> pd.DataFrame:
    from signal_engine import resolve_symbol
    broker = resolve_symbol(symbol)
    if not broker:
        raise RuntimeError(f"{symbol} no existe en el broker")
    tf_code = getattr(mt5, f"TIMEFRAME_{tf}")
    end = datetime.now(timezone.utc)
    rates = None
    # Desde el año más antiguo que el terminal acepte: un rango con más de `maxbars` velas da "Invalid params"
    for year in START_YEARS:
        for _ in range(3):  # la primera petición puede disparar la descarga del historial en el terminal
            rates = mt5.copy_rates_range(broker, tf_code, datetime(year, 1, 1, tzinfo=timezone.utc), end)
            if rates is not None and len(rates):
                break
            time.sleep(0.5)
        if rates is not None and len(rates):
            break
    if rates is None or not len(rates):
        raise RuntimeError(f"Sin historial {tf} para {broker}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df = merge_rates(load_rates(symbol, tf), df.iloc[:-1])  # la última vela aún no está cerrada
    CACHE_DIR.mkdir(exist_ok=True)
    info = mt5.symbol_info(broker)
    with open(rates_path(symbol, tf), "wb") as f:
        pickle.dump({"broker": broker, "point": info.point, "digits": info.digits,
                     "contract_size": info.trade_contract_size, "rates": df}, f)
    return df


SPECS_PATH = CACHE_DIR / "specs.json"


def save_specs(mt5) -> dict:
    """Especificación actual de cada símbolo, incluido el swap (para costes de posiciones de varios días)."""
    from signal_engine import resolve_symbol
    out = {"medido": datetime.now(timezone.utc).isoformat(timespec="seconds"), "simbolos": {}}
    for sym in SYMBOLS:
        info = mt5.symbol_info(resolve_symbol(sym))
        out["simbolos"][sym] = {
            "broker": info.name, "point": info.point, "digits": info.digits,
            "contract_size": info.trade_contract_size, "swap_mode": info.swap_mode,
            "swap_long": info.swap_long, "swap_short": info.swap_short,
            "swap_rollover3days": info.swap_rollover3days, "currency_profit": info.currency_profit,
        }
    CACHE_DIR.mkdir(exist_ok=True)
    SPECS_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def spread_stats(tick_spreads: np.ndarray, bar_spreads_px: np.ndarray) -> dict:
    """Spread típico real (ticks) frente al de las velas (que el backtest usa) y la diferencia a cobrar."""
    s = tick_spreads[tick_spreads > 0]
    if not len(s):
        return {"ticks": 0}
    p50_bar = float(np.median(bar_spreads_px)) if len(bar_spreads_px) else 0.0
    return {
        "ticks": int(len(s)),
        "tick_p50": float(np.median(s)),
        "tick_p90": float(np.percentile(s, 90)),
        "tick_mean": float(s.mean()),
        "bar_p50": p50_bar,
        "spread_extra_px": max(0.0, float(np.median(s)) - p50_bar),
    }


def measure_spreads(mt5, days: int = 3) -> dict:
    from signal_engine import resolve_symbol
    end = datetime.now(timezone.utc)
    out = {"medido": end.isoformat(timespec="seconds"), "dias": days, "servidor": mt5.account_info().server,
           "simbolos": {}}
    for sym in SYMBOLS:
        broker = resolve_symbol(sym)
        info = mt5.symbol_info(broker)
        ticks = mt5.copy_ticks_range(broker, end - timedelta(days=days), end, mt5.COPY_TICKS_INFO)
        bars = mt5.copy_rates_range(broker, mt5.TIMEFRAME_M5, end - timedelta(days=days), end)
        if ticks is None or bars is None:
            out["simbolos"][sym] = {"error": str(mt5.last_error())}
            continue
        out["simbolos"][sym] = spread_stats(ticks["ask"] - ticks["bid"], bars["spread"] * info.point)
        print(sym, out["simbolos"][sym])
    CACHE_DIR.mkdir(exist_ok=True)
    SPREADS_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "rates"
    mt5 = connect()
    try:
        if cmd == "spreads":
            measure_spreads(mt5, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
        elif cmd == "specs":
            print(json.dumps(save_specs(mt5), indent=2))
        else:
            tfs = [a.upper() for a in sys.argv[2:]] or ["D1", "H1"]
            for tf in tfs:
                if tf not in TF_NAMES:
                    sys.exit(f"Marco temporal no soportado: {tf}")
                for sym in SYMBOLS:
                    df = download_rates(mt5, sym, tf)
                    first = datetime.fromtimestamp(int(df["time"].iloc[0]), timezone.utc).date()
                    last = datetime.fromtimestamp(int(df["time"].iloc[-1]), timezone.utc).date()
                    print(f"{sym} {tf}: {len(df)} velas {first} → {last}")
    finally:
        mt5.shutdown()
