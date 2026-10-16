"""Prueba a futuro en sombra (fase 4): mide las estrategias con reglas CONGELADAS sobre datos posteriores a la
congelación, sin enviar ninguna orden.

Los datos que aún no existían al congelar no sufren el problema de los 22 intentos: son la única prueba limpia.
- MOTOR: el motor de señales en vivo (backtest_frames) sobre M5/M15/H1 posteriores a la congelación.
- H-B:   momentum de 12 meses en D1 (research/hipotesis/h_b.py) con sus operaciones mensuales posteriores.
Ambos netos de costes (costs.py). Si cambia el código de las reglas, el informe lo marca: el resultado deja de valer.

Uso:
    python forward.py freeze     # congela (una sola vez): guarda fecha y huellas de los archivos de reglas
    python forward.py run        # recalcula forward_results.json (MT5 abierto)
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "forward_config.json"
RESULTS_PATH = ROOT / "forward_results.json"
RULE_FILES = ["setups.py", "signal_engine.py", "backtest.py", "costs.py", "research/hipotesis/h_b.py"]
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "US100", "USDJPY"]
# Lo que dijeron los backtests (media neta por operación): el forward se compara contra esto
EXPECTED_R = {"MOTOR": -0.04, "H-B": 0.067}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(root: Path = ROOT, config_path: Path = CONFIG_PATH, now: datetime | None = None) -> dict:
    if config_path.exists():
        raise RuntimeError(f"Ya congelado ({config_path.name}); descongelar invalida la prueba a futuro")
    now = now or datetime.now(timezone.utc)
    cfg = {
        "congelado": now.isoformat(timespec="seconds"),
        "freeze_ts": now.timestamp(),
        "huellas": {f: file_hash(root / f) for f in RULE_FILES},
        "esperado_r": EXPECTED_R,
    }
    config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def load_config(config_path: Path = CONFIG_PATH) -> dict | None:
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def changed_rules(cfg: dict, root: Path = ROOT) -> list[str]:
    """Archivos de reglas cuyo contenido cambió desde la congelación (o que ya no existen)."""
    out = []
    for f, h in cfg["huellas"].items():
        p = root / f
        if not p.exists() or file_hash(p) != h:
            out.append(f)
    return out


def closed_after(trades: list[dict], freeze_ts: float, last_bar_idx: int) -> tuple[list[dict], int]:
    """Operaciones del motor con señal posterior a la congelación y ya terminadas. Una que acabó 'por tiempo'
    justo en la última vela disponible sigue abierta en realidad: se cuenta aparte."""
    done, still_open = [], 0
    for t in trades:
        if t["t"] <= freeze_ts:
            continue
        if t.get("outcome") == "TIEMPO" and t.get("exit_idx", 0) >= last_bar_idx:
            still_open += 1
            continue
        done.append(t)
    return done, still_open


def tsmom_current(df, spec: dict) -> dict | None:
    """Posición de H-B en curso (el periodo de 21 sesiones que aún no terminó), con las mismas reglas de h_b."""
    from research.hipotesis.h_b import HOLD, LOOKBACK, VOL_WINDOW
    df = df.sort_values("time").reset_index(drop=True)
    n = len(df)
    if n < LOOKBACK + 2:
        return None
    k = LOOKBACK + ((n - 2 - LOOKBACK) // HOLD) * HOLD  # último rebalanceo con vela de entrada disponible
    if k + 1 + HOLD < n:
        return None  # ese periodo ya terminó (lo cuenta tsmom_trades)
    c, o, t = df["close"].to_numpy(float), df["open"].to_numpy(float), df["time"].to_numpy(float)
    signal = c[k] / c[k - LOOKBACK] - 1
    rets = c[1:] / c[:-1] - 1
    sigma = float(np.std(rets[k - VOL_WINDOW:k], ddof=1))
    if signal == 0 or not sigma > 0:
        return None
    return {
        "direccion": "BUY" if signal > 0 else "SELL",
        "desde": datetime.fromtimestamp(t[k + 1], timezone.utc).date().isoformat(),
        "entrada": float(o[k + 1]),
        "sesiones_restantes": int(k + 1 + HOLD - (n - 1)),
        "riesgo_px": round(float(o[k + 1]) * sigma * math.sqrt(HOLD), 6),
    }


def summarize(trades: list[dict], strategy: str) -> dict:
    from research.robustness import report
    rep = report(trades, n_trials=1) if trades else {"n": 0}
    rep["esperado_r"] = EXPECTED_R[strategy]
    rep["por_simbolo"] = {s: {"n": sum(1 for t in trades if t["symbol"] == s),
                              "avg_r": round(float(np.mean([t["r"] for t in trades if t["symbol"] == s])), 3)}
                          for s in sorted({t["symbol"] for t in trades})}
    return rep


def run(mt5) -> dict:
    import backtest
    from costs import apply_costs, extra_cost_px
    from research import data
    from research.hipotesis.h_b import tsmom_trades
    from signal_engine import resolve_symbol

    cfg = load_config()
    if cfg is None:
        raise RuntimeError("Sin congelar: ejecuta python forward.py freeze")
    freeze_ts = cfg["freeze_ts"]
    days = max(10, int((datetime.now(timezone.utc).timestamp() - freeze_ts) / 86400) + 10)

    motor, motor_open = [], 0
    for sym in SYMBOLS:
        broker = resolve_symbol(sym)
        info = mt5.symbol_info(broker)
        frames = backtest.fetch_frames(broker, days)
        cost = extra_cost_px(sym, price=float(frames["m5"]["close"].iloc[-1]))
        res = backtest.backtest_frames(frames, info.point, info.digits, cost_px=cost)
        done, still_open = closed_after(res["trades_nuevo"], freeze_ts, len(frames["m5"]) - 1)
        motor += [{**t, "symbol": sym} for t in done]
        motor_open += still_open

    specs = data.save_specs(mt5)["simbolos"]
    hb, hb_now = [], {}
    for sym in SYMBOLS:
        df = data.download_rates(mt5, sym, "D1")
        trades = [t for t in tsmom_trades(df, sym, specs[sym]) if t["t"] > freeze_ts]
        hb += apply_costs(trades, extra_cost_px(sym, price=float(df["close"].iloc[-1])))
        cur = tsmom_current(df, specs[sym])
        if cur:
            hb_now[sym] = cur

    out = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "congelado": cfg["congelado"],
        "reglas_modificadas": changed_rules(cfg),
        "MOTOR": {**summarize(motor, "MOTOR"), "abiertas_sin_terminar": motor_open},
        "H-B": summarize(hb, "H-B"),
        "H-B_posiciones_en_sombra": hb_now,
    }
    RESULTS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=float), encoding="utf-8")
    return out


def load_results() -> dict | None:
    try:
        return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "freeze":
        print(json.dumps(freeze(), ensure_ascii=False, indent=2))
    else:
        from research.data import connect
        m = connect()
        try:
            r = run(m)
        finally:
            m.shutdown()
        print(f"Congelado {r['congelado']} · reglas modificadas: {r['reglas_modificadas'] or 'ninguna'}")
        for k in ("MOTOR", "H-B"):
            x = r[k]
            print(f"  {k}: n={x['n']} media {x.get('avg_r')}R (esperado {x['esperado_r']}R) t={x.get('t_stat')}")
        print("  H-B en sombra ahora:", r["H-B_posiciones_en_sombra"])
