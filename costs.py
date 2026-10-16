"""Modelo de costes por símbolo para los backtests (constitución, principio 2).

El backtest ya cobra un spread por operación, pero toma el de las velas de MT5, que es el MÍNIMO de cada vela:
en XAUUSD la mediana de las velas M5 es 0.15 y la de los ticks reales 0.39 (medido el 15-oct-2026 en MetaQuotes-Demo).
Aquí se suma, por operación completa (ida y vuelta) y en unidades de precio:

- spread_extra_px  diferencia entre el spread típico de los ticks y el de las velas (medido: research/data.py spreads)
- slippage_px      deslizamiento supuesto en entrada + salida a mercado
- commission_usd_per_lot  comisión de ida y vuelta por lote (0 en MetaQuotes-Demo; tu broker real puede cobrar)

`costes.json` (junto a este archivo) puede sobrescribir cualquier valor por símbolo.
"""
from __future__ import annotations

import json
from pathlib import Path

COSTS_PATH = Path(__file__).with_name("costes.json")

# Valores por defecto. spread_extra_px: medido (p50 ticks − p50 velas M5, 2 días, research/cache/spreads.json).
# slippage_px: deslizamiento + diferencia con un broker real. El demo cotiza EURUSD/GBPUSD con 0.1 pip, irreal para
# una cuenta estándar, así que el total por operación se fija como en el estrés de INFORME_VARIANTES.md
# (EURUSD 0.5 pip, GBPUSD 0.8, USDJPY 0.8, US100 1.0 punto) y el oro suma el spread medido + 0.10.
DEFAULT_COSTS: dict[str, dict] = {
    "XAUUSD": {"spread_extra_px": 0.24, "slippage_px": 0.10, "commission_usd_per_lot": 0.0, "contract_size": 100.0},
    "EURUSD": {"spread_extra_px": 0.00001, "slippage_px": 0.00004, "commission_usd_per_lot": 0.0, "contract_size": 100000.0},
    "GBPUSD": {"spread_extra_px": 0.00001, "slippage_px": 0.00007, "commission_usd_per_lot": 0.0, "contract_size": 100000.0},
    "USDJPY": {"spread_extra_px": 0.002, "slippage_px": 0.006, "commission_usd_per_lot": 0.0, "contract_size": 100000.0,
               "quote_in_usd": False},
    "US100": {"spread_extra_px": 0.0, "slippage_px": 1.0, "commission_usd_per_lot": 0.0, "contract_size": 1.0},
}


def load_costs(path: Path = COSTS_PATH) -> dict[str, dict]:
    costs = {k: dict(v) for k, v in DEFAULT_COSTS.items()}
    try:
        override = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return costs
    for sym, values in override.get("simbolos", {}).items():
        costs.setdefault(sym, {}).update(values)
    return costs


def extra_cost_px(symbol: str, price: float | None = None, costs: dict | None = None) -> float:
    """Coste extra por operación completa en unidades de precio (lo que el backtest aún no cobra)."""
    c = (costs or load_costs()).get(symbol)
    if not c:
        return 0.0
    commission_px = 0.0
    if c.get("commission_usd_per_lot"):
        # 1 unidad de precio con 1 lote vale contract_size en la divisa cotizada; USDJPY cotiza en JPY
        per_unit_usd = c["contract_size"] / (price if (c.get("quote_in_usd") is False and price) else 1.0)
        commission_px = c["commission_usd_per_lot"] / per_unit_usd
    return c.get("spread_extra_px", 0.0) + c.get("slippage_px", 0.0) + commission_px


def apply_costs(trades: list[dict], cost_px: float) -> list[dict]:
    """Copia de las operaciones con 'r' neto: r − coste / riesgo. Guarda el bruto en 'r_bruto'."""
    out = []
    for t in trades:
        risk = t.get("risk_px") or 0.0
        cost_r = cost_px / risk if risk > 0 else 0.0
        out.append({**t, "r_bruto": t["r"], "r": t["r"] - cost_r, "coste_r": cost_r})
    return out


# Modos de swap de MT5 (ENUM_SYMBOL_SWAP_MODE) que se pueden convertir a unidades de precio
SWAP_MODE_POINTS = 1
SWAP_MODES_MONEY_PER_LOT = (2, 3, 4)  # en divisa del símbolo, de margen o de la cuenta (USD en este demo)


def swap_cost_px_per_night(spec: dict, direction: str) -> float:
    """Coste de swap por noche en unidades de precio (≥ 0). Los swaps positivos no se cuentan como ingreso."""
    swap = spec["swap_long"] if direction == "BUY" else spec["swap_short"]
    if spec.get("swap_mode") == SWAP_MODE_POINTS:
        px = swap * spec["point"]
    elif spec.get("swap_mode") in SWAP_MODES_MONEY_PER_LOT:
        px = swap / spec["contract_size"]
    else:
        raise ValueError(f"Modo de swap no soportado: {spec.get('swap_mode')}")
    return max(0.0, -px)
