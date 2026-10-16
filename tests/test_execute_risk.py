import os
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from main import cap_volume  # noqa: E402

client = TestClient(main.app)


# ---------- Recorte puro ----------

def test_cap_volume_keeps_volume_within_risk():
    assert cap_volume(0.10, 0.25, False, 1.0) == (0.10, None)


def test_cap_volume_reduces_but_never_increases():
    vol, msg = cap_volume(2.0, 0.25, False, 1.0)
    assert vol == 0.25 and "reducido" in msg


@pytest.mark.parametrize("requested,exceeds", [(0.0, False), (-1.0, False), (0.01, True)])
def test_cap_volume_rejects(requested, exceeds):
    vol, msg = cap_volume(requested, 0.25, exceeds, 1.0)
    assert vol is None and msg


# ---------- /execute recorta antes de enviar ----------

@pytest.fixture
def live_broker(monkeypatch):
    sent = {}

    def fake_send(broker_symbol, direction, volume, sl, tp1, tp2, magic, comment):
        sent.update(volume=volume, magic=magic, tp1=tp1, tp2=tp2)
        r = SimpleNamespace(order=555, price=1.1000, request=SimpleNamespace(price=1.0999))
        if tp1:
            half = round(volume / 2, 2)
            r2 = SimpleNamespace(order=556, price=1.1000, request=SimpleNamespace(price=1.0999))
            return [(r, half, "TP1"), (r2, half, "TP2")], None
        return [(r, volume, "UNICA")], None

    monkeypatch.setattr(main, "is_mt5_live", lambda: True)
    monkeypatch.setattr(main, "resolve_symbol", lambda s: s)
    monkeypatch.setattr(main.kill_switch, "state", {"locked": False, "lock_reason": ""})
    monkeypatch.setattr(main.mt5, "symbol_info_tick", lambda s: SimpleNamespace(bid=1.1000, ask=1.1002))
    monkeypatch.setattr(main.engine, "calculate_lot_size", lambda *a, **k: (0.30, False))
    monkeypatch.setattr(main, "send_plan_orders", fake_send)
    monkeypatch.setattr(main.bot_copilot, "log_event", lambda *a, **k: None)
    saved = []

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def add(self, row):
            saved.append(row)

        def commit(self):
            pass

    monkeypatch.setattr(main, "SessionLocal", FakeDB)
    return sent, saved


ORDER = {"symbol": "EURUSD", "direction": "BUY", "sl": 1.0950, "tp": 1.1100, "score": 67}


def test_execute_sends_requested_volume_when_within_risk(live_broker):
    sent, saved = live_broker
    r = client.post("/execute", json={**ORDER, "volume": 0.20})
    assert r.status_code == 200 and r.json()["volume"] == 0.20 and r.json()["risk_note"] is None
    assert sent["volume"] == 0.20 and sent["magic"] == main.MAGIC_NUMBER
    assert saved[0].signal_score == 67


def test_execute_caps_oversized_volume(live_broker):
    sent, _ = live_broker
    r = client.post("/execute", json={**ORDER, "volume": 5.0})
    assert r.status_code == 200 and sent["volume"] == 0.30
    assert "reducido" in r.json()["risk_note"]


def test_execute_rejects_when_min_lot_exceeds_risk(live_broker, monkeypatch):
    sent, _ = live_broker
    monkeypatch.setattr(main.engine, "calculate_lot_size", lambda *a, **k: (0.01, True))
    r = client.post("/execute", json={**ORDER, "volume": 0.01})
    assert r.status_code == 400 and "lote mínimo" in r.json()["detail"] and not sent


def test_execute_with_tp1_records_two_legs_sharing_group(live_broker):
    sent, saved = live_broker
    r = client.post("/execute", json={**ORDER, "volume": 0.20, "tp1": 1.1050})
    body = r.json()
    assert r.status_code == 200 and body["tickets"] == [555, 556] and body["volume"] == 0.2
    assert "dos órdenes" in body["risk_note"]
    tp1_leg, tp2_leg = saved
    assert (tp1_leg.leg, tp2_leg.leg) == ("TP1", "TP2") and tp1_leg.group_id == tp2_leg.group_id == 555
    assert tp1_leg.tp_initial == 1.1050 and tp2_leg.tp_initial == 1.1100
    assert tp1_leg.tp1 is None and tp2_leg.tp1 is None  # el parcial lo hace el broker, no la app
    assert tp1_leg.requested_price == 1.0999


def test_execute_without_tp1_is_single_order_managed_by_app(live_broker):
    sent, saved = live_broker
    client.post("/execute", json={**ORDER, "volume": 0.20})
    assert len(saved) == 1 and saved[0].leg == "UNICA" and saved[0].group_id is None
