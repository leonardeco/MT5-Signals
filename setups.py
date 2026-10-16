"""Plan de entrada de una señal: zona, gatillo M5, SL/TP por estructura y ciclo de vida.

Módulo puro (sin MT5) para que el escáner en vivo y el backtest usen exactamente la misma lógica.
"""
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

# Zona de entrada alrededor de la EMA 21 M15 (en compras; espejo en ventas)
ZONE_ABOVE_ATR = 0.2
ZONE_BELOW_ATR = 0.6
ZONE_MAX_WIDTH_ATR = 1.2
FVG_MERGE_ATR = 0.5

# Stop por estructura: debajo del mínimo reciente / zona, con colchón y límites de distancia
SL_BUFFER_ATR = 0.25
SL_MIN_ATR = 0.75
SL_MAX_ATR = 3.0

# Objetivos en niveles de liquidez
MIN_RR_TP1 = 1.0          # si la primera liquidez en contra está a menos de 1R → sin espacio
FAR_TP1_RR = 3.0          # si la primera liquidez está a más de 3R, TP1 se toma en 1.5R
MAX_TP_RR = 5.0
LEVEL_NOISE_RR = 0.2      # niveles a menos de 0.2R de la entrada se ignoran

# Ciclo de vida
SETUP_TTL_SECONDS = 3600        # 4 velas M15 para llegar a la zona y disparar el gatillo
ACTIVATION_TTL_SECONDS = 600    # 2 velas M5 para ejecutar una vez activada
MOVED_AWAY_RR = 0.5             # si el precio ya avanzó 0.5R desde el gatillo, la entrada se perdió

PREPARANDO, EN_ZONA, ACTIVADA = "PREPARANDO", "EN_ZONA", "ACTIVADA"
EXPIRADA, INVALIDADA, DESCARTADA, SIN_SETUP = "EXPIRADA", "INVALIDADA", "DESCARTADA", "SIN_SETUP"
STICKY_STATES = {EXPIRADA, INVALIDADA}


@dataclass
class TradePlan:
    direction: str
    zone_low: float
    zone_high: float
    entry: float
    sl: float
    tp1: float
    tp2: float
    tp1_label: str
    tp2_label: str
    risk: float
    rr_tp1: float
    rr_tp2: float
    valid: bool
    invalid_kind: str = ""      # "broken" (precio rompió la invalidación) | "no_space" | "wide_sl"
    invalid_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Estructura: swings, FVG y niveles de liquidez
# ---------------------------------------------------------------------------

def swing_indices(highs: np.ndarray, lows: np.ndarray, k: int = 2) -> tuple[np.ndarray, np.ndarray]:
    """Fractales confirmados: el máximo/mínimo de una ventana de 2k+1 velas (requiere k velas posteriores)."""
    n = len(highs)
    if n < 2 * k + 1:
        return np.array([], dtype=int), np.array([], dtype=int)
    win = 2 * k + 1
    hw = np.lib.stride_tricks.sliding_window_view(highs, win)
    lw = np.lib.stride_tricks.sliding_window_view(lows, win)
    centers = np.arange(k, n - k)
    sh = centers[hw[:, k] == hw.max(axis=1)]
    sl = centers[lw[:, k] == lw.min(axis=1)]
    return sh, sl


def recent_fvg(opens, highs, lows, closes, direction: str, lookback: int = 10) -> Optional[tuple[float, float]]:
    """FVG más reciente a favor de la dirección dentro de las últimas `lookback` velas cerradas."""
    n = len(closes)
    for j in range(n - 1, max(1, n - lookback) - 1, -1):
        if j < 2:
            break
        if direction == "BUY" and lows[j] > highs[j - 2] and closes[j - 1] > opens[j - 1]:
            return float(highs[j - 2]), float(lows[j])
        if direction == "SELL" and highs[j] < lows[j - 2] and closes[j - 1] < opens[j - 1]:
            return float(highs[j]), float(lows[j - 2])
    return None


def collect_levels(m15_high, m15_low, h1_high, h1_low, prev_day=None, prev_week=None) -> list[dict]:
    """Niveles de liquidez a partir de velas CERRADAS: swings M15 (≈1 día), swings H1 (≈5 días), día y semana anteriores."""
    levels: list[dict] = []
    m15_high, m15_low = np.asarray(m15_high, float)[-96:], np.asarray(m15_low, float)[-96:]
    h1_high, h1_low = np.asarray(h1_high, float)[-120:], np.asarray(h1_low, float)[-120:]
    sh, sl = swing_indices(m15_high, m15_low, k=2)
    levels += [{"name": "Máximo M15", "price": float(m15_high[i])} for i in sh]
    levels += [{"name": "Mínimo M15", "price": float(m15_low[i])} for i in sl]
    sh, sl = swing_indices(h1_high, h1_low, k=2)
    levels += [{"name": "Máximo H1", "price": float(h1_high[i])} for i in sh]
    levels += [{"name": "Mínimo H1", "price": float(h1_low[i])} for i in sl]
    if prev_day is not None:
        levels += [{"name": "Máx. día anterior", "price": float(prev_day[0])},
                   {"name": "Mín. día anterior", "price": float(prev_day[1])}]
    if prev_week is not None:
        levels += [{"name": "Máx. semana anterior", "price": float(prev_week[0])},
                   {"name": "Mín. semana anterior", "price": float(prev_week[1])}]
    return levels


# ---------------------------------------------------------------------------
# Plan: zona, SL y objetivos
# ---------------------------------------------------------------------------

def _plan_long(ema21, atr, swing_low, fvg, levels, price) -> dict:
    """Plan en 'espacio de compra'. Las ventas se resuelven negando precios (ver build_plan)."""
    z_hi = ema21 + ZONE_ABOVE_ATR * atr
    z_lo = ema21 - ZONE_BELOW_ATR * atr
    if fvg is not None:
        f_lo, f_hi = fvg
        if f_hi >= z_lo - FVG_MERGE_ATR * atr and f_lo <= z_hi + FVG_MERGE_ATR * atr:
            z_lo, z_hi = min(z_lo, f_lo), max(z_hi, f_hi)
    z_lo = max(z_lo, z_hi - ZONE_MAX_WIDTH_ATR * atr)

    # Mientras el precio no llega a la zona, se planifica con el borde de la zona (mejor precio)
    entry = price if price <= z_hi else z_hi
    sl = min(swing_low, z_lo) - SL_BUFFER_ATR * atr
    out = {"zone_low": z_lo, "zone_high": z_hi, "entry": entry, "valid": True, "invalid_kind": "", "invalid_reason": ""}

    if price <= sl:
        risk = max(entry - sl, SL_MIN_ATR * atr)
        out.update(sl=sl, risk=risk, tp1=entry + risk, tp2=entry + 2 * risk, tp1_label="-", tp2_label="-",
                   valid=False, invalid_kind="broken", invalid_reason="El precio rompió el nivel de invalidación (SL)")
        return out

    risk = entry - sl
    if risk < SL_MIN_ATR * atr:
        sl = entry - SL_MIN_ATR * atr
        risk = SL_MIN_ATR * atr
    out.update(sl=sl, risk=risk)
    if risk > SL_MAX_ATR * atr:
        out.update(tp1=entry + risk, tp2=entry + 2 * risk, tp1_label="-", tp2_label="-", valid=False,
                   invalid_kind="wide_sl", invalid_reason=f"SL estructural demasiado amplio ({risk / atr:.1f} ATR)")
        return out

    targets = sorted((lv for lv in levels if lv["price"] > entry + LEVEL_NOISE_RR * risk), key=lambda lv: lv["price"])
    if not targets:
        out.update(tp1=entry + 1.5 * risk, tp1_label="1.5R (sin liquidez cercana)",
                   tp2=entry + 3 * risk, tp2_label="3R")
        return out

    first = targets[0]
    first_rr = (first["price"] - entry) / risk
    if first_rr < MIN_RR_TP1:
        out.update(tp1=first["price"], tp2=first["price"], tp1_label=first["name"], tp2_label=first["name"],
                   valid=False, invalid_kind="no_space",
                   invalid_reason=f"Sin espacio: {first['name']} a solo {first_rr:.2f}R")
        return out

    if first_rr > FAR_TP1_RR:
        out.update(tp1=entry + 1.5 * risk, tp1_label="1.5R",
                   tp2=min(first["price"], entry + MAX_TP_RR * risk), tp2_label=first["name"])
        return out

    tp1 = first["price"]
    nxt = next((lv for lv in targets[1:] if tp1 + 0.5 * risk <= lv["price"] <= entry + MAX_TP_RR * risk), None)
    if nxt:
        tp2, tp2_label = nxt["price"], nxt["name"]
    else:
        tp2, tp2_label = entry + max(2 * risk, (tp1 - entry) + risk), "Extensión"
    out.update(tp1=tp1, tp1_label=first["name"], tp2=tp2, tp2_label=tp2_label)
    return out


def build_plan(direction: str, ema21: float, atr: float, recent_lows, recent_highs, fvg, levels: list[dict],
               price_now: float, digits: int) -> TradePlan:
    """price_now: ask para compras, bid para ventas."""
    if direction == "BUY":
        p = _plan_long(ema21, atr, float(np.min(recent_lows)), fvg, levels, price_now)
        zl, zh, entry, sl, tp1, tp2 = p["zone_low"], p["zone_high"], p["entry"], p["sl"], p["tp1"], p["tp2"]
    else:
        neg_fvg = (-fvg[1], -fvg[0]) if fvg is not None else None
        neg_levels = [{"name": lv["name"], "price": -lv["price"]} for lv in levels]
        p = _plan_long(-ema21, atr, -float(np.max(recent_highs)), neg_fvg, neg_levels, -price_now)
        zl, zh = -p["zone_high"], -p["zone_low"]
        entry, sl, tp1, tp2 = -p["entry"], -p["sl"], -p["tp1"], -p["tp2"]
    risk = p["risk"]
    r = lambda v: round(float(v), digits)  # noqa: E731
    return TradePlan(
        direction=direction, zone_low=r(zl), zone_high=r(zh), entry=r(entry), sl=r(sl), tp1=r(tp1), tp2=r(tp2),
        tp1_label=p["tp1_label"], tp2_label=p["tp2_label"], risk=float(risk),
        rr_tp1=round(abs(tp1 - entry) / risk, 2) if risk > 0 else 0.0,
        rr_tp2=round(abs(tp2 - entry) / risk, 2) if risk > 0 else 0.0,
        valid=p["valid"], invalid_kind=p["invalid_kind"], invalid_reason=p["invalid_reason"],
    )


def price_in_zone(plan: TradePlan, price: float) -> bool:
    """Compra: el precio bajó al techo de la zona (o más). Venta: subió al piso de la zona."""
    return price <= plan.zone_high if plan.direction == "BUY" else price >= plan.zone_low


# ---------------------------------------------------------------------------
# Gatillo en M5
# ---------------------------------------------------------------------------

def m5_trigger(opens, highs, lows, closes, plan: TradePlan) -> Optional[str]:
    """Evalúa la ÚLTIMA vela M5 cerrada (arrays con al menos 4 velas cerradas). Devuelve el nombre del gatillo o None.

    Solo envolvente y pin bar: la ruptura de estructura M5 se retiró porque perdía −0.37R por operación,
    en los 5 pares y en los 5 bloques temporales del backtest de 340 días (research/INFORME_VARIANTES.md).
    """
    if len(closes) < 4 or not plan.valid:
        return None
    o, h, l, c = float(opens[-1]), float(highs[-1]), float(lows[-1]), float(closes[-1])
    po, pc = float(opens[-2]), float(closes[-2])
    rng = h - l
    body = abs(c - o)
    if rng <= 0:
        return None
    if plan.direction == "BUY":
        touched = l <= plan.zone_high and c >= plan.zone_low and l > plan.sl
        if not touched:
            return None
        if pc < po and c > o and c >= po and o <= pc:
            return "Envolvente alcista M5"
        lower_wick = min(o, c) - l
        if lower_wick >= 2 * body and lower_wick >= 0.5 * rng and (c - l) >= 0.6 * rng:
            return "Pin bar alcista M5"
    else:
        touched = h >= plan.zone_low and c <= plan.zone_high and h < plan.sl
        if not touched:
            return None
        if pc > po and c < o and c <= po and o >= pc:
            return "Envolvente bajista M5"
        upper_wick = h - max(o, c)
        if upper_wick >= 2 * body and upper_wick >= 0.5 * rng and (h - c) >= 0.6 * rng:
            return "Pin bar bajista M5"
    return None


# ---------------------------------------------------------------------------
# Ciclo de vida de la señal
# ---------------------------------------------------------------------------

class SetupTracker:
    """Recuerda cada setup entre escaneos: PREPARANDO → EN_ZONA → ACTIVADA, o EXPIRADA / INVALIDADA.

    `now` es un reloj en segundos (time.time() en vivo, cierre de vela en el backtest).
    Los tiempos de vela (`signal_bar_close`, `trigger_bar_close`) van en la hora del servidor de MT5.
    """

    def __init__(self, ttl: int = SETUP_TTL_SECONDS, activation_ttl: int = ACTIVATION_TTL_SECONDS):
        self.ttl = ttl
        self.activation_ttl = activation_ttl
        self._setups: dict[str, dict] = {}

    def live_direction(self, symbol: str) -> Optional[str]:
        s = self._setups.get(symbol)
        return s["direction"] if s and s["state"] not in STICKY_STATES else None

    def get(self, symbol: str) -> Optional[dict]:
        return self._setups.get(symbol)

    def clear(self, symbol: str):
        self._setups.pop(symbol, None)

    def update(self, symbol: str, plan: TradePlan, price_now: float, now: float,
               signal_bar_close: Optional[float] = None, origin_score: int = 0,
               trigger: Optional[str] = None, trigger_bar_close: Optional[float] = None) -> dict:
        """signal_bar_close: cierre de la vela M15 que generó señal en este escaneo (None si solo se arrastra un setup)."""
        s = self._setups.get(symbol)
        fresh = (
            s is None
            or (signal_bar_close is not None and s["direction"] != plan.direction)
            or (signal_bar_close is not None and s["state"] in STICKY_STATES
                and signal_bar_close > s["origin_bar_close"])
        )
        if fresh:
            s = {
                "direction": plan.direction, "state": PREPARANDO, "created": now,
                "origin_bar_close": signal_bar_close or 0.0, "origin_score": origin_score,
                "activated_at": None, "trigger": None, "trigger_price": None, "risk": plan.risk, "reason": "",
            }
            self._setups[symbol] = s

        if s["state"] in STICKY_STATES:
            return self._view(s, now)

        if s["state"] == ACTIVADA:
            moved = (price_now - s["trigger_price"]) if plan.direction == "BUY" else (s["trigger_price"] - price_now)
            if now - s["activated_at"] > self.activation_ttl:
                s.update(state=EXPIRADA, reason="Gatillo sin ejecutar a tiempo")
            elif moved > MOVED_AWAY_RR * s["risk"]:
                s.update(state=EXPIRADA, reason="Entrada perdida: el precio ya se alejó")
            return self._view(s, now)

        if now - s["created"] > self.ttl:
            s.update(state=EXPIRADA, reason="El precio no dio gatillo en la zona a tiempo")
        elif not plan.valid:
            if plan.invalid_kind == "broken":
                s.update(state=INVALIDADA, reason=plan.invalid_reason)
            else:
                s.update(state=DESCARTADA, reason=plan.invalid_reason)
        elif trigger and (trigger_bar_close or 0) > s["origin_bar_close"]:
            s.update(state=ACTIVADA, activated_at=now, trigger=trigger, trigger_price=price_now,
                     risk=plan.risk, reason="")
        elif price_in_zone(plan, price_now):
            s.update(state=EN_ZONA, reason="")
        else:
            s.update(state=PREPARANDO, reason="")
        return self._view(s, now)

    def _view(self, s: dict, now: float) -> dict:
        if s["state"] == ACTIVADA:
            remaining = self.activation_ttl - (now - s["activated_at"])
        elif s["state"] in STICKY_STATES:
            remaining = 0
        else:
            remaining = self.ttl - (now - s["created"])
        return {
            "state": s["state"],
            "trigger": s["trigger"],
            "state_reason": s["reason"],
            "expires_in": max(0, int(remaining)),
            "origin_score": s["origin_score"],
            "origin_bar_close": s["origin_bar_close"],
        }
