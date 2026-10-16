"""Laboratorio: evalúa UNA hipótesis registrada con costes reales y métricas de robustez.

Flujo (constitución, principios 2 y 3):
1. La hipótesis tiene que estar en research/registro_hipotesis.json con su criterio (research/registry.py).
2. Su código vive en research/hipotesis/<id en minúsculas, '-' → '_'>.py y expone `run() -> list[dict]`:
   una operación por elemento con 'symbol', 't' (epoch de la señal), 'r' (bruto, en R) y 'risk_px'.
3. Aquí se descuentan los costes de costs.py, se calcula el informe de robustez con el nº total de intentos,
   se compara con el criterio y se guarda el resultado (una sola vez para hipótesis; los controles se repiten).

Uso:  python -m research.lab C-MOTOR-ACTUAL
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from costs import apply_costs, extra_cost_px, load_costs  # noqa: E402
from research import registry  # noqa: E402
from research.robustness import passes, report  # noqa: E402

RESULTS_DIR = Path(__file__).with_name("resultados")


def module_name(hid: str) -> str:
    return "research.hipotesis." + hid.lower().replace("-", "_")


def net_trades(trades: list[dict], costs: dict | None = None) -> list[dict]:
    """Descuenta el coste de cada símbolo (con el precio de la operación si lo trae, para la comisión en JPY)."""
    costs = costs or load_costs()
    out = []
    for t in trades:
        out += apply_costs([t], extra_cost_px(t["symbol"], price=t.get("price"), costs=costs))
    return out


def evaluate(hid: str, trades: list[dict], n_trials: int, criterio: dict, costs: dict | None = None) -> dict:
    net = net_trades(trades, costs)
    symbols = sorted({t["symbol"] for t in net})
    total = report(net, n_trials)
    ok, fails = passes(total, criterio)
    return {
        "id": hid,
        "n_trials": n_trials,
        "criterio": criterio,
        "pasa": ok,
        "fallos": fails,
        "coste_medio_r": round(sum(t["coste_r"] for t in net) / len(net), 3) if net else 0.0,
        "media_bruta_r": round(sum(t["r_bruto"] for t in net) / len(net), 3) if net else None,
        "total": total,
        "por_simbolo": {s: report([t for t in net if t["symbol"] == s], n_trials) for s in symbols},
    }


def run(hid: str) -> dict:
    entry = registry.get(hid)
    if entry is None:
        raise registry.RegistryError(f"'{hid}' no está registrada: usa research.registry.register(...) antes")
    if entry["tipo"] == "hipotesis" and entry["estado"] != "registrada":
        raise registry.RegistryError(f"'{hid}' ya se evaluó ({entry['estado']})")
    trades = importlib.import_module(module_name(hid)).run()
    result = evaluate(hid, trades, registry.n_trials(), entry["criterio"] or dict(registry.DEFAULT_CRITERIO))
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / f"{hid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    registry.record_result(hid, {k: result[k] for k in ("pasa", "fallos", "coste_medio_r", "media_bruta_r", "total")},
                           result["pasa"])
    return result


def print_summary(res: dict) -> None:
    tot = res["total"]
    print(f"\n{res['id']}  ({res['n_trials']} intentos registrados)  →  {'PASA' if res['pasa'] else 'NO PASA'}")
    for f in res["fallos"]:
        print(f"   ✗ {f}")
    print(f"  Total: n={tot['n']}  media bruta {res['media_bruta_r']}R  coste {res['coste_medio_r']}R  "
          f"neta {tot['avg_r']}R  t={tot['t_stat']}  IC95 {tot['ic95_media']}  DSR={tot['dsr']}  "
          f"DD p95={tot['drawdown_r'] and tot['drawdown_r']['p95']}R")
    print(f"  Tramos: antiguo {tot['tramo_antiguo']}  reciente {tot['tramo_reciente']}")
    print(f"  Bloques: {[b['avg_r'] for b in tot['bloques']]}")
    for sym, r in res["por_simbolo"].items():
        print(f"    {sym:7s} n={r['n']:4d}  neta {r['avg_r']}R  t={r['t_stat']}  "
              f"antiguo {r['tramo_antiguo']['avg_r']}  reciente {r['tramo_reciente']['avg_r']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit("Uso: python -m research.lab <ID registrado>")
    print_summary(run(sys.argv[1]))
