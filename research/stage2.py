"""Segunda fase: tablas por par, walk-forward, estrés de costes y significancia de las variantes que sobrevivieron.

Uso:  python research/stage2.py [dias_cache]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest import summarize  # noqa: E402
from research.explore_variants import (  # noqa: E402
    HERE, VARIANTS, common_cutoff, features, fixed_rr, load, run_variant, split, trig_is, nothing,
)

# Coste extra por operación (precio) además del spread de las velas: deslizamiento + spread más ancho en vivo
EXTRA_COST = {"XAUUSD": 0.20, "EURUSD": 0.00005, "GBPUSD": 0.00008, "USDJPY": 0.008, "US100": 1.0}
N_BLOCKS = 5
FOCUS = ["BASE", "G2 solo pin bar", "G4 sin ruptura", "X3 fijo 2R", "G2+X3 (combinación)"]
SPECS = dict(VARIANTS)
SPECS["G2+X3 (combinación)"] = ("combinación", None, trig_is("Pin bar"), fixed_rr(2.0), nothing)
TRIGGER_FAMILY = ["BASE", "G1 solo envolvente", "G2 solo pin bar", "G3 solo ruptura", "G4 sin ruptura"]


def boot_ci(rs: np.ndarray, n_boot: int = 5000, seed: int = 7) -> tuple[float, float]:
    if len(rs) < 2:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = rng.choice(rs, size=(n_boot, len(rs)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def tstat(rs: np.ndarray) -> float:
    return float(rs.mean() / (rs.std(ddof=1) / np.sqrt(len(rs)))) if len(rs) > 2 else float("nan")


def with_costs(trades_by_sym: dict) -> dict:
    return {s: [{**t, "r": t["r"] - EXTRA_COST[s] / t["risk_px"]} for t in tr] for s, tr in trades_by_sym.items()}


def blocks(data: dict) -> np.ndarray:
    start = max(float(v["frames"]["m5"]["time"].iloc[0]) for v in data.values())
    end = min(float(v["frames"]["m5"]["time"].iloc[-1]) for v in data.values())
    edges = np.linspace(start, end, N_BLOCKS + 1)
    edges[0], edges[-1] = -np.inf, np.inf   # el historial previo de XAU/US100 cae en el bloque 1
    return edges


def block_means(trades_by_sym: dict, edges) -> list[dict]:
    all_tr = [t for tr in trades_by_sym.values() for t in tr]
    out = []
    for k in range(N_BLOCKS):
        rs = np.array([t["r"] for t in all_tr if edges[k] <= t["t"] < edges[k + 1]])
        out.append({"n": int(len(rs)), "avg_r": round(float(rs.mean()), 3) if len(rs) else 0.0,
                    "total_r": round(float(rs.sum()), 2)})
    return out


def main(days: int):
    data = load(days)
    feats = {s: features(v["frames"]) for s, v in data.items()}
    cutoff = common_cutoff(data)
    edges = blocks(data)
    print("bloques:", [str(pd.to_datetime(e, unit="s").date()) for e in edges[1:-1]])

    runs = {name: run_variant(data, feats, name, SPECS[name]) for name in dict.fromkeys(FOCUS + TRIGGER_FAMILY)}
    report = {"cutoff": cutoff, "edges": edges[1:-1].tolist(), "focus": {}, "wf": {}}

    for name in FOCUS:
        tr = runs[name]
        per = {}
        for sym, lst in tr.items():
            a, b = split(lst, cutoff)
            per[sym] = {"is": summarize(a), "oos": summarize(b)}
        all_tr = [t for lst in tr.values() for t in lst]
        a, b = split(all_tr, cutoff)
        per["TOTAL"] = {"is": summarize(a), "oos": summarize(b)}
        rs_all, rs_oos = np.array([t["r"] for t in all_tr]), np.array([t["r"] for t in b])
        cost = with_costs(tr)
        ca = [t for lst in cost.values() for t in lst]
        c_is, c_oos = split(ca, cutoff)
        report["focus"][name] = {
            "per_pair": per,
            "t_all": round(tstat(rs_all), 2), "ci_all": boot_ci(rs_all),
            "t_oos": round(tstat(rs_oos), 2), "ci_oos": boot_ci(rs_oos),
            "with_costs": {"is": summarize(c_is), "oos": summarize(c_oos)},
            "blocks": block_means(tr, edges),
        }
        f = report["focus"][name]
        print(f"\n== {name}  t(todo)={f['t_all']}  IC95 OOS={tuple(round(x, 3) for x in f['ci_oos'])}")
        for sym, st in per.items():
            i, o = st["is"], st["oos"]
            print(f"  {sym:7s} IS n={i['n']:3d} {i['win_rate']:5.1f}% {i['avg_r']:+.3f}R PF={i['profit_factor']} racha={i['max_losing_streak']:2d}"
                  f" | OOS n={o['n']:3d} {o['win_rate']:5.1f}% {o['avg_r']:+.3f}R PF={o['profit_factor']} racha={o['max_losing_streak']:2d}")
        print("  con costes extra: IS", f["with_costs"]["is"]["avg_r"], " OOS", f["with_costs"]["oos"]["avg_r"])
        print("  bloques:", [b["avg_r"] for b in f["blocks"]], [b["n"] for b in f["blocks"]])

    # Walk-forward: en cada bloque k≥2 se elige la variante de gatillo con mejor media R en los bloques < k
    fam_blocks = {name: block_means(runs[name], edges) for name in TRIGGER_FAMILY}
    chosen, wf_rs = [], []
    for k in range(1, N_BLOCKS):
        def past(name):
            bl = fam_blocks[name][:k]
            n = sum(b["n"] for b in bl)
            return sum(b["total_r"] for b in bl) / n if n else -9
        best = max(TRIGGER_FAMILY, key=past)
        chosen.append(best)
        wf_rs.append(fam_blocks[best][k])
    n = sum(b["n"] for b in wf_rs)
    wf_avg = sum(b["total_r"] for b in wf_rs) / n if n else 0.0
    report["wf"] = {"chosen": chosen, "blocks": wf_rs, "avg_r": round(wf_avg, 3), "n": n,
                    "family_blocks": fam_blocks}
    print("\nWalk-forward (familia de gatillos):", chosen, [b["avg_r"] for b in wf_rs], f"media={wf_avg:+.3f}R n={n}")
    for name in TRIGGER_FAMILY:
        print(f"  {name:20s}", [b["avg_r"] for b in fam_blocks[name]])

    # Diagnóstico: base por tipo de gatillo y por par
    base = [dict(t, sym=s) for s, lst in runs["BASE"].items() for t in lst]
    df = pd.DataFrame(base)
    df["tipo"] = df["trigger"].str.extract(r"^(Envolvente|Pin bar|Ruptura)")
    print("\nBase por tipo de gatillo:\n", df.groupby(["tipo"]).r.agg(["count", "mean", "sum"]).round(3))
    print(df.groupby(["sym", "tipo"]).r.agg(["count", "mean"]).round(3).unstack())
    (HERE / f"stage2_{days}d.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float),
                                              encoding="utf-8")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 340)
