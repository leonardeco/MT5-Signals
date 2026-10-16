import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import execution  # noqa: E402


class FakeMT5:
    TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL, ORDER_TIME_GTC = 1, 0, 1, 0
    ORDER_FILLING_IOC, ORDER_FILLING_FOK, ORDER_FILLING_RETURN = 1, 0, 2
    SYMBOL_TRADE_MODE_DISABLED = 0

    def __init__(self, send_codes, vmin=0.01, step=0.01):
        self.send_codes = list(send_codes)
        self.sent, self.ticks = [], 0
        self.info = SimpleNamespace(name="EURUSD", digits=5, point=0.00001, trade_stops_level=0, trade_freeze_level=0,
                                    volume_min=vmin, volume_max=100.0, volume_step=step, filling_mode=2, trade_mode=4)

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(trade_allowed=True)

    def symbol_info(self, s):
        return self.info

    def symbol_info_tick(self, s):
        self.ticks += 1
        p = 1.1000 + self.ticks * 0.0001
        return SimpleNamespace(bid=p, ask=p + 0.0001)

    def order_check(self, req):
        return SimpleNamespace(retcode=0, comment="")

    def order_send(self, req):
        code = self.send_codes.pop(0) if self.send_codes else 10009
        self.sent.append(dict(req))
        return SimpleNamespace(retcode=code, comment="", order=1000 + len(self.sent), price=req["price"],
                               request=SimpleNamespace(price=req["price"]))

    def last_error(self):
        return (0, "")


@pytest.fixture
def fake(monkeypatch):
    def make(codes, **kw):
        f = FakeMT5(codes, **kw)
        monkeypatch.setattr(execution, "mt5", f)
        monkeypatch.setattr(execution, "RETRY_PAUSE_SECONDS", 0)
        return f
    return make


def test_requote_is_retried_with_fresh_price(fake):
    f = fake([10004, 10009])
    result, err, vol = execution.send_market_order("EURUSD", "BUY", 0.1, 1.0900, 1.1200, 7, "t")
    assert result and err is None and len(f.sent) == 2
    assert f.sent[1]["price"] > f.sent[0]["price"]  # segundo intento con el tick nuevo
    assert execution.requested_price(result) == pytest.approx(f.sent[1]["price"])


def test_retries_are_limited_and_other_errors_are_not_retried(fake):
    f = fake([10004] * 5)
    result, err, _ = execution.send_market_order("EURUSD", "BUY", 0.1, 1.0900, 1.1200, 7, "t")
    assert result is None and "Recotización" in err and len(f.sent) == execution.MAX_PRICE_RETRIES
    f = fake([10019])
    result, err, _ = execution.send_market_order("EURUSD", "BUY", 0.1, 1.0900, 1.1200, 7, "t")
    assert result is None and "Fondos insuficientes" in err and len(f.sent) == 1


def test_split_volume_rounds_down_to_step():
    assert execution.split_volume(0.25, 0.01, 0.01) == 0.12
    assert execution.split_volume(0.01, 0.01, 0.01) is None
    assert execution.split_volume(3, 1, 1) == 1


def test_plan_orders_split_in_two_legs_with_tp1_and_tp2(fake):
    f = fake([])
    legs, err = execution.send_plan_orders("EURUSD", "BUY", 0.2, 1.0900, 1.1050, 1.1200, 7, "Q")
    assert err is None and [leg for _, _, leg in legs] == ["TP1", "TP2"]
    assert [r["tp"] for r in f.sent] == [1.105, 1.12] and [r["volume"] for r in f.sent] == [0.1, 0.1]
    assert all(r["sl"] == 1.09 for r in f.sent)


def test_plan_orders_single_when_half_is_below_min_lot_or_no_tp1(fake):
    f = fake([])
    legs, _ = execution.send_plan_orders("EURUSD", "BUY", 0.01, 1.0900, 1.1050, 1.1200, 7, "Q")
    assert [leg for _, _, leg in legs] == ["UNICA"] and f.sent[0]["tp"] == 1.12
    f = fake([])
    legs, _ = execution.send_plan_orders("EURUSD", "BUY", 0.2, 1.0900, None, 1.1200, 7, "Q")
    assert [leg for _, _, leg in legs] == ["UNICA"] and f.sent[0]["volume"] == 0.2


def test_plan_orders_report_when_second_leg_fails(fake):
    fake([10009, 10019])
    legs, err = execution.send_plan_orders("EURUSD", "BUY", 0.2, 1.0900, 1.1050, 1.1200, 7, "Q")
    assert [leg for _, _, leg in legs] == ["TP1"] and "Solo se abrió la mitad" in err
