"""Contexto y lista de verificación de una señal para quien opera a mano.

No cambia ninguna regla congelada (setups.py, signal_engine.py, backtest.py, costs.py): solo lee el resultado del
motor y añade información para decidir.

- trend_12m: signo del retorno de 12 meses en D1, la misma medida que la hipótesis H-B (research/hipotesis/h_b.py),
  la única con resultado positivo tras costes (+0.067R, t 2.22) aunque no demostrado (DSR 0.61 < 0.95).
- cost_r: lo que cuesta la operación (spread actual + coste extra de costs.py) en múltiplos del riesgo.
- checklist: condiciones que un operador revisaría antes de entrar. NO es una probabilidad de acierto: en el
  backtest, sumar puntos de score no predijo mejores resultados.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from research.hipotesis.h_b import LOOKBACK as TREND_LOOKBACK

MAX_COST_R = 0.10           # por encima, el coste se come la mayor parte de cualquier ventaja pequeña
HARD_CHECKS = ("plan", "trigger", "lot", "news", "exposure")  # si falla uno de estos, no se debería entrar


def trend_12m(closes) -> Optional[dict]:
    """Dirección del retorno de los últimos TREND_LOOKBACK cierres D1 (velas cerradas, la última al final)."""
    c = np.asarray(closes, dtype=float)
    if len(c) < TREND_LOOKBACK + 1 or not c[-1 - TREND_LOOKBACK] > 0:
        return None
    ret = c[-1] / c[-1 - TREND_LOOKBACK] - 1.0
    if ret == 0 or not np.isfinite(ret):
        return None
    return {"direction": "BUY" if ret > 0 else "SELL", "return_pct": round(float(ret) * 100, 1)}


def cost_r(spread_px: float, extra_px: float, entry: float, sl: float) -> Optional[float]:
    """Coste de ida y vuelta (spread + deslizamiento/comisión de costs.py) dividido por el riesgo del plan."""
    risk = abs(entry - sl)
    if not risk > 0:
        return None
    return round((max(0.0, spread_px) + max(0.0, extra_px)) / risk, 3)


def is_carried(sig: dict) -> bool:
    """El setup viene de una vela M15 anterior: los pilares mostrados son de la vela actual, no de la de señal."""
    return any("sigue vigente" in r for r in sig.get("reasons", []))


def _item(key: str, label: str, ok: Optional[bool], detail: str = "") -> dict:
    return {"key": key, "label": label, "ok": ok, "detail": detail}


def checklist(sig: dict, trend: Optional[dict], cost: Optional[float]) -> list[dict]:
    """Condiciones de la señal, cada una ok=True/False, o None si no se puede saber."""
    direction = sig.get("direction")
    pillars = sig.get("pillars") or {}
    env = sig.get("environment") or {}
    state = sig.get("state")
    carried = is_carried(sig)
    na = "setup de una vela anterior" if carried else ""

    def pillar(key: str):
        return None if carried else pillars.get(key, 0) > 0

    plan_ok = None if state in (None, "SIN_SETUP") else (
        state not in ("DESCARTADA", "INVALIDADA") and (sig.get("rr_tp1") or 0) >= 1.0)
    items = [
        _item("h1", "Tendencia H1 a favor (EMA 50/200)", pillar("macro_h1"), na),
        _item("pullback", "Retroceso a la EMA 21 en M15", pillar("structure_m15"), na),
        _item("momentum", "Impulso MACD/RSI a favor", pillar("momentum"), na),
        _item("plan", "Espacio ≥ 1R hasta la liquidez", plan_ok,
              sig.get("state_reason") or (f"TP1 a {sig.get('rr_tp1')}R" if sig.get("rr_tp1") else "")),
        _item("trigger", "Gatillo M5 confirmado", state == "ACTIVADA" if state else None, sig.get("trigger") or ""),
        _item("cost", f"Coste ≤ {MAX_COST_R:.2f}R", None if cost is None else cost <= MAX_COST_R,
              "" if cost is None else f"{cost:.2f}R"),
        _item("lot", "Lote dentro del riesgo por operación", not sig.get("lot_exceeds_risk", False)),
        _item("session", "Sesión activa", env.get("session_ok") if env else None),
        _item("news", "Sin noticias de alto impacto", (not env.get("news_blocked")) if env else None,
              env.get("news_message", "") if env.get("news_blocked") else ""),
        _item("exposure", "Exposición por divisa libre", env.get("correlation_ok") if env else None,
              "" if env.get("correlation_ok", True) else env.get("correlation_message", "")),
        _item("trend12", "A favor de la tendencia de 12 meses", None if not trend else trend["direction"] == direction,
              "" if not trend else f"{trend['return_pct']:+.1f}% en 12 meses"),
        _item("edge", "Ventaja demostrada en el backtest", bool(sig.get("auto_eligible"))),
    ]
    return items


def summarize_checklist(items: list[dict]) -> dict:
    known = [i for i in items if i["ok"] is not None]
    blockers = [i["label"] for i in items if i["key"] in HARD_CHECKS and i["ok"] is False]
    return {"passed": sum(1 for i in known if i["ok"]), "total": len(known), "blockers": blockers}


def plan_money(mt5, broker_symbol: str, direction: str, lot: float, entry: float, sl: float,
               tp1: Optional[float], tp2: Optional[float]) -> Optional[dict]:
    """Dinero en riesgo y a ganar con el lote recomendado (order_calc_profit de MT5: incluye la conversión de divisa).
    Con TP1, la mitad del lote cierra en TP1 y la otra mitad en TP2, como el plan."""
    if not lot or lot <= 0 or not sl:
        return None
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    def pnl(volume: float, price: float) -> Optional[float]:
        try:
            v = mt5.order_calc_profit(order_type, broker_symbol, volume, entry, price)
        except Exception:
            return None
        return float(v) if v is not None else None

    risk = pnl(lot, sl)
    if risk is None:
        return None
    out = {"risk": round(abs(risk), 2)}
    if tp1 and tp2:
        a, b = pnl(lot / 2, tp1), pnl(lot / 2, tp2)
        if a is not None and b is not None:
            out["tp1"], out["tp2"] = round(a, 2), round(a + b, 2)
    elif tp2:
        b = pnl(lot, tp2)
        if b is not None:
            out["tp2"] = round(b, 2)
    return out


def annotate(sig: dict, trend: Optional[dict], spread_px: float, extra_px: float) -> dict:
    """Añade trend_12m, cost_r, checklist y su resumen a una señal BUY/SELL (las NEUTRAL no cambian)."""
    if sig.get("direction") not in ("BUY", "SELL"):
        return sig
    sig["trend_12m"] = trend
    sig["cost_r"] = cost_r(spread_px, extra_px, sig.get("entry_price", 0.0), sig.get("sl", 0.0))
    items = checklist(sig, trend, sig["cost_r"])
    sig["checklist"] = items
    sig["checklist_summary"] = summarize_checklist(items)
    return sig


def stale_execution_reason(direction: str, latest: Optional[dict]) -> Optional[str]:
    """Motivo para rechazar una orden manual si la señal que vio el panel ya no está vigente en el motor.
    Sin señal del escáner para ese símbolo (arranque, tests) no se bloquea."""
    if not latest or latest.get("data_source") != "MT5":
        return None
    if latest.get("direction") != direction.upper():
        return f"La señal de {latest.get('symbol')} cambió a {latest.get('direction')}"
    state = latest.get("state")
    if state is not None and state != "ACTIVADA":
        return f"La señal de {latest.get('symbol')} ya no está activada ({state}): la ventana de entrada pasó"
    return None
