import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import signal_context as sc  # noqa: E402
from database import should_give_up_on_history  # noqa: E402
from quant_bot_copilot import QuantBotCopilot  # noqa: E402


# ---------- Tendencia de 12 meses (misma medida que H-B) ----------

def test_trend_12m_sign_and_return():
    closes = np.linspace(100, 120, sc.TREND_LOOKBACK + 1)
    t = sc.trend_12m(closes)
    assert t == {"direction": "BUY", "return_pct": 20.0}
    assert sc.trend_12m(closes[::-1])["direction"] == "SELL"


def test_trend_12m_uses_exactly_lookback_bars():
    closes = np.full(sc.TREND_LOOKBACK + 10, 100.0)
    closes[-1 - sc.TREND_LOOKBACK] = 90.0  # solo cuenta el cierre de hace LOOKBACK sesiones
    assert sc.trend_12m(closes)["direction"] == "BUY"


@pytest.mark.parametrize("closes", [np.ones(10), np.full(400, 100.0), np.zeros(400)])
def test_trend_12m_none_when_not_computable(closes):
    assert sc.trend_12m(closes) is None


# ---------- Coste en R ----------

def test_cost_r_divides_spread_plus_extra_by_risk():
    assert sc.cost_r(0.30, 0.10, entry=2000.0, sl=1996.0) == 0.1
    assert sc.cost_r(0.30, 0.10, entry=2000.0, sl=2000.0) is None


# ---------- Lista de verificación ----------

def buy_signal(**kw):
    sig = {
        "symbol": "XAUUSD", "direction": "BUY", "state": "ACTIVADA", "rr_tp1": 1.4, "trigger": "Pin bar alcista M5",
        "pillars": {"macro_h1": 25, "structure_m15": 25, "smc_liquidity": 0, "momentum": 0, "execution_cost": 0},
        "environment": {"session_ok": True, "news_blocked": False, "news_message": "", "correlation_ok": True,
                        "correlation_message": ""},
        "lot_exceeds_risk": False, "auto_eligible": False, "reasons": ["Tendencia alcista H1"],
        "entry_price": 2000.0, "sl": 1996.0,
    }
    sig.update(kw)
    return sig


def by_key(items):
    return {i["key"]: i["ok"] for i in items}


def test_checklist_reads_pillars_state_environment_and_trend():
    items = sc.checklist(buy_signal(), {"direction": "SELL", "return_pct": -5.0}, cost=0.05)
    ok = by_key(items)
    assert ok["h1"] and ok["pullback"] and ok["momentum"] is False
    assert ok["plan"] and ok["trigger"] and ok["cost"] and ok["lot"]
    assert ok["trend12"] is False and ok["edge"] is False


def test_checklist_marks_plan_blockers():
    items = sc.checklist(buy_signal(state="DESCARTADA", state_reason="Sin espacio"), None, cost=0.2)
    ok = by_key(items)
    assert ok["plan"] is False and ok["trigger"] is False and ok["cost"] is False and ok["trend12"] is None
    summary = sc.summarize_checklist(items)
    assert "Espacio ≥ 1R hasta la liquidez" in summary["blockers"]
    assert "Gatillo M5 confirmado" in summary["blockers"]


def test_checklist_unknown_pillars_for_carried_setup():
    sig = buy_signal(reasons=["Setup BUY de una vela M15 anterior sigue vigente"])
    ok = by_key(sc.checklist(sig, None, None))
    assert ok["h1"] is None and ok["pullback"] is None and ok["cost"] is None


def test_annotate_leaves_neutral_untouched_and_fills_buy():
    neutral = {"direction": "NEUTRAL"}
    assert sc.annotate(dict(neutral), None, 0.3, 0.1) == neutral
    sig = sc.annotate(buy_signal(), {"direction": "BUY", "return_pct": 12.0}, 0.30, 0.10)
    assert sig["cost_r"] == 0.1 and sig["trend_12m"]["direction"] == "BUY"
    assert sig["checklist_summary"]["total"] == len(sig["checklist"])
    assert sig["checklist_summary"]["blockers"] == []


# ---------- Dinero en riesgo / objetivo ----------

class FakeCalc:
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1

    def order_calc_profit(self, order_type, symbol, volume, open_price, close_price):
        diff = (close_price - open_price) if order_type == 0 else (open_price - close_price)
        return diff * volume * 100.0


def test_plan_money_splits_half_at_tp1():
    m = sc.plan_money(FakeCalc(), "XAUUSD", "BUY", 0.10, 2000.0, 1996.0, 2004.0, 2008.0)
    assert m == {"risk": 40.0, "tp1": 20.0, "tp2": 60.0}
    assert sc.plan_money(FakeCalc(), "XAUUSD", "SELL", 0.10, 2000.0, 2004.0, None, 1992.0) == {"risk": 40.0, "tp2": 80.0}
    assert sc.plan_money(FakeCalc(), "XAUUSD", "BUY", 0.0, 2000.0, 1996.0, None, 2008.0) is None


# ---------- Orden manual con una señal que ya cambió ----------

def test_stale_execution_reason():
    live = {"symbol": "EURUSD", "direction": "BUY", "state": "ACTIVADA", "data_source": "MT5"}
    assert sc.stale_execution_reason("buy", live) is None
    assert "cambió a SELL" in sc.stale_execution_reason("BUY", {**live, "direction": "SELL"})
    assert "EXPIRADA" in sc.stale_execution_reason("BUY", {**live, "state": "EXPIRADA"})
    assert sc.stale_execution_reason("BUY", None) is None
    assert sc.stale_execution_reason("BUY", {**live, "data_source": "OFFLINE"}) is None


# ---------- Copilot: bitácora sin repeticiones y lote no divisible ----------

def test_signal_log_not_flooded_by_alternating_symbols():
    bot = QuantBotCopilot()
    before = len(bot.activity_logs)
    for _ in range(5):
        for sym in ("XAUUSD", "USDJPY"):
            bot.enrich_signal_with_bot_telemetry(
                {"symbol": sym, "direction": "BUY", "score": 90, "reasons": [], "pillars": {"smc_liquidity": 0},
                 "state": "ACTIVADA", "origin_bar_close": 1.0}, None)
    assert len(bot.activity_logs) - before == 2


@pytest.mark.parametrize("volume,expected", [(0.01, False), (0.02, True), (0.03, True), (0.06, True)])
def test_can_split_respects_min_lot_and_float_steps(volume, expected):
    # 0.06 * 0.5 / 0.01 = 2.9999999999999996 en coma flotante: sin margen se redondeaba a 0.02 en vez de 0.03
    sym = SimpleNamespace(volume_min=0.01, volume_step=0.01)
    assert QuantBotCopilot.can_split(volume, sym) is expected


# ---------- Bitácora: no dar por cerrada sin historial demasiado pronto ----------

def test_history_wait_counts_from_disappearance():
    seen = {}
    t0 = datetime(2026, 11, 16, 12, 0)
    assert should_give_up_on_history(7, t0, seen) is False
    assert should_give_up_on_history(7, t0 + timedelta(minutes=5), seen) is False
    assert should_give_up_on_history(7, t0 + timedelta(minutes=11), seen) is True
    assert 7 not in seen
