import os
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

# Sin "with": no arranca el lifespan (ni MT5 ni el escáner)
client = TestClient(main.app)
EVIL = "https://pagina-cualquiera.example"
FRONT = "http://localhost:5180"
VIEW = "https://panel-publicado.example"


@pytest.fixture
def read_only_origin(monkeypatch):
    monkeypatch.setattr(main, "READ_ORIGINS", {VIEW})
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", main.TRADE_ORIGINS | {VIEW})


def test_post_from_foreign_origin_is_rejected_before_reaching_the_endpoint(monkeypatch):
    called = []
    monkeypatch.setattr(main.kill_switch, "emergency_close_all", lambda: called.append(1) or 0)
    r = client.post("/close-all", headers={"origin": EVIL})
    assert r.status_code == 403 and not called


def test_post_from_local_frontend_is_allowed(monkeypatch):
    monkeypatch.setattr(main.bot_copilot, "set_mode", lambda mode: {"mode": mode})
    assert client.post("/bot/mode", json={"mode": "SNIPER"}, headers={"origin": FRONT}).status_code == 200


def test_post_without_origin_is_allowed_for_local_scripts(monkeypatch):
    monkeypatch.setattr(main.bot_copilot, "set_mode", lambda mode: {"mode": mode})
    assert client.post("/bot/mode", json={"mode": "SNIPER"}).status_code == 200


def test_cors_preflight_only_for_local_frontend():
    pre = {"access-control-request-method": "POST", "access-control-request-headers": "content-type"}
    ok = client.options("/execute", headers={"origin": FRONT, **pre})
    bad = client.options("/execute", headers={"origin": EVIL, **pre})
    assert ok.headers.get("access-control-allow-origin") == FRONT
    assert "access-control-allow-origin" not in bad.headers


def test_websocket_from_foreign_origin_is_closed():
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/signals", headers={"origin": EVIL}) as ws:
            ws.receive_text()
    assert exc.value.code == 1008


def test_websocket_from_local_frontend_connects():
    with client.websocket_connect("/ws/signals", headers={"origin": FRONT}):
        assert len(main.clients.connections) >= 1


def test_read_only_origin_cannot_touch_the_account(monkeypatch, read_only_origin):
    called = []
    monkeypatch.setattr(main.kill_switch, "emergency_close_all", lambda: called.append(1) or 0)
    r = client.post("/close-all", headers={"origin": VIEW})
    assert r.status_code == 403 and not called
    assert "solo lectura" in r.json()["detail"]


def test_read_only_origin_can_read_and_knows_it(read_only_origin):
    body = client.get("/status", headers={"origin": VIEW}).json()
    assert body["can_trade"] is False
    assert client.get("/status", headers={"origin": FRONT}).json()["can_trade"] is True


def test_status_identifies_the_service():
    body = client.get("/status").json()
    assert body["service"] == "mt5-senales"
    assert body["local_panel"] == "http://localhost:5180"


def test_origins_file_is_read_only_unless_marked():
    trade, read = main.parse_origins_file(
        "# comentario\n"
        "https://panel.example/\n"
        "https://operar.example operar\n"
        "https://otro.example lectura  # nota\n"
    )
    assert trade == {"https://operar.example"}
    assert read == {"https://panel.example", "https://otro.example"}


def test_market_snapshot_is_available_before_the_scanner_runs():
    body = client.get("/market").json()
    assert body["type"] == "MARKET_UPDATE"
    assert body["signals"] == []
    assert "balance" in body["account"]


def test_private_network_header_only_for_allowed_origin():
    pre = {
        "access-control-request-method": "GET",
        "access-control-request-private-network": "true",
    }
    ok = client.options("/market", headers={"origin": FRONT, **pre})
    bad = client.options("/market", headers={"origin": EVIL, **pre})
    assert ok.status_code == 200
    assert ok.headers.get("access-control-allow-private-network") == "true"
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers
