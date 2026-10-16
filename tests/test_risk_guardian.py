import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk_guardian  # noqa: E402
from risk_guardian import DailyKillSwitch  # noqa: E402

BOT, OTHER = 202605, 0


class FakeMT5:
    POSITION_TYPE_BUY, ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 0, 1
    TRADE_ACTION_DEAL, ORDER_TIME_GTC, ORDER_FILLING_IOC, ORDER_FILLING_FOK = 1, 0, 1, 0
    TRADE_RETCODE_DONE = 10009

    def __init__(self, positions):
        self.positions, self.sent = positions, []

    def positions_get(self):
        return self.positions

    def symbol_info(self, symbol):
        return SimpleNamespace(filling_mode=2)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=1.0, ask=1.1)

    def order_send(self, req):
        self.sent.append(req)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE)


def pos(ticket, magic):
    return SimpleNamespace(ticket=ticket, magic=magic, symbol="EURUSD", volume=0.1, type=0)


def test_emergency_close_only_touches_bot_positions(monkeypatch):
    fake = FakeMT5([pos(1, BOT), pos(2, OTHER), pos(3, BOT), pos(4, 999)])
    monkeypatch.setattr(risk_guardian, "mt5", fake)
    assert DailyKillSwitch(magic=BOT).emergency_close_all() == 2
    assert sorted(r["position"] for r in fake.sent) == [1, 3]


def test_emergency_close_without_positions(monkeypatch):
    monkeypatch.setattr(risk_guardian, "mt5", FakeMT5(None))
    assert DailyKillSwitch(magic=BOT).emergency_close_all() == 0
