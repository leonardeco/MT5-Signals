import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import quant_bot_copilot  # noqa: E402
from quant_bot_copilot import QuantBotCopilot  # noqa: E402


class FakeMT5:
    POSITION_TYPE_BUY, TRADE_ACTION_SLTP, TRADE_RETCODE_DONE, TIMEFRAME_M15 = 0, 6, 10009, 15

    def __init__(self, positions):
        self.positions, self.sent = positions, []

    def positions_get(self, magic=None):
        return self.positions

    def symbol_info(self, s):
        return SimpleNamespace(digits=5, point=0.00001, volume_min=0.01, volume_step=0.01)

    def symbol_info_tick(self, s):
        return SimpleNamespace(bid=1.1050, ask=1.1051)

    def copy_rates_from_pos(self, *a):
        return None

    def order_send(self, req):
        self.sent.append(req)
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE)


def pos(ticket, current, sl=1.0950):
    return SimpleNamespace(ticket=ticket, type=0, symbol="EURUSD", volume=0.1, price_open=1.1000,
                           price_current=current, sl=sl, tp=1.1200)


def run(monkeypatch, positions, meta):
    fake = FakeMT5(positions)
    monkeypatch.setattr(quant_bot_copilot, "mt5", fake)
    QuantBotCopilot().manage_smart_trailing_and_partials(7, None, meta)
    return fake.sent


META = {556: {"leg": "TP2", "group_id": 555}, 555: {"leg": "TP1", "group_id": 555}}


def test_tp2_leg_moves_to_breakeven_once_tp1_leg_closed(monkeypatch):
    sent = run(monkeypatch, [pos(556, 1.1060)], META)
    assert len(sent) == 1 and sent[0]["position"] == 556 and sent[0]["sl"] == 1.1


def test_tp2_leg_waits_while_tp1_leg_is_open(monkeypatch):
    assert run(monkeypatch, [pos(555, 1.1060), pos(556, 1.1060)], META) == []


def test_tp2_leg_not_moved_if_losing_or_already_at_breakeven(monkeypatch):
    assert run(monkeypatch, [pos(556, 1.0990)], META) == []
    assert run(monkeypatch, [pos(556, 1.1060, sl=1.1000)], META) == []
