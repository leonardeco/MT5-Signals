"""Motor en un VPS: con claves activas, nada responde sin clave válida (salvo /status) y solo la de operar opera."""
import os
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
from engine_auth import (  # noqa: E402
    AccessKeys, bearer_from_header, bearer_from_subprotocols, keys_from_env, load_env_file,
)

client = TestClient(main.app)
TRADE = "t" * 43
READ = "r" * 43
PANEL = "https://mt5-signals.vercel.app"
EVIL = "https://pagina-cualquiera.example"


@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setattr(main, "KEYS", AccessKeys(TRADE, READ))
    monkeypatch.setattr(main, "READ_ORIGINS", {PANEL})
    monkeypatch.setattr(main, "ALLOWED_ORIGINS", main.TRADE_ORIGINS | {PANEL})
    monkeypatch.setattr(main.bot_copilot, "set_mode", lambda mode: {"mode": mode})


def auth(token):
    return {"authorization": f"Bearer {token}", "origin": PANEL}


# ---------- Piezas puras ----------

def test_access_keys_levels_and_validation():
    k = AccessKeys(TRADE, READ)
    assert k.enabled and k.level(TRADE) == "operar" and k.level(READ) == "lectura"
    assert k.level("x" * 43) is None and k.level(None) is None and k.level("") is None
    assert not AccessKeys().enabled
    with pytest.raises(ValueError, match="demasiado corta"):
        AccessKeys("corta")
    with pytest.raises(ValueError, match="distintas"):
        AccessKeys(TRADE, TRADE)


def test_token_extraction():
    assert bearer_from_header("Bearer abc") == "abc" and bearer_from_header("bearer  abc ") == "abc"
    assert bearer_from_header("Basic abc") is None and bearer_from_header(None) is None
    assert bearer_from_subprotocols("bearer, abc") == "abc"
    assert bearer_from_subprotocols("chat") is None and bearer_from_subprotocols(None) is None


def test_env_file_does_not_override_existing_variables(tmp_path):
    f = tmp_path / "motor.env"
    f.write_text("# comentario\nMT5_TOKEN_OPERAR = \"abc\"\nMT5_PATH=C:/x\nmal formada\n", encoding="utf-8")
    env = {"MT5_PATH": "ya definida"}
    assert load_env_file(f, env) == ["MT5_TOKEN_OPERAR"]
    assert env == {"MT5_PATH": "ya definida", "MT5_TOKEN_OPERAR": "abc"}
    assert load_env_file(tmp_path / "no-existe.env", env) == []
    assert keys_from_env({"MT5_TOKEN_LECTURA": READ}).level(READ) == "lectura"


# ---------- HTTP ----------

def test_everything_but_status_needs_a_key(keys):
    assert client.get("/market").status_code == 401
    assert client.get("/market", headers={"origin": PANEL}).status_code == 401
    assert client.get("/market", headers=auth("x" * 43)).status_code == 401
    assert client.get("/market", headers=auth(READ)).status_code == 200


def test_curl_without_origin_is_no_longer_trusted(keys, monkeypatch):
    called = []
    monkeypatch.setattr(main.kill_switch, "emergency_close_all", lambda: called.append(1) or 0)
    assert client.post("/close-all").status_code == 401 and not called


def test_status_without_key_reveals_only_identity(keys):
    body = client.get("/status", headers={"origin": PANEL}).json()
    assert body["service"] == "mt5-senales" and body["auth_required"] is True and body["authenticated"] is False
    assert "watchlist" not in body and "autotrading" not in body and "magic" not in body
    full = client.get("/status", headers=auth(READ)).json()
    assert full["authenticated"] is True and full["can_trade"] is False and "watchlist" in full
    assert client.get("/status", headers=auth(TRADE)).json()["can_trade"] is True


def test_read_key_cannot_trade_and_trade_key_can(keys):
    r = client.post("/bot/mode", json={"mode": "SNIPER"}, headers=auth(READ))
    assert r.status_code == 403 and "solo lectura" in r.json()["detail"]
    assert client.post("/bot/mode", json={"mode": "SNIPER"}, headers=auth(TRADE)).status_code == 200


def test_valid_key_from_unknown_website_is_rejected(keys):
    r = client.post("/bot/mode", json={"mode": "SNIPER"}, headers={"authorization": f"Bearer {TRADE}", "origin": EVIL})
    assert r.status_code == 401


def test_preflight_still_works_without_key(keys):
    # El navegador no manda la clave en el preflight: si se exigiera, ninguna petición con clave llegaría a salir.
    # (La lista de CORS se fija al arrancar; en el VPS el panel publicado va en allowed_origins.local.)
    local = "http://localhost:5180"
    pre = {"origin": local, "access-control-request-method": "POST",
           "access-control-request-headers": "authorization,content-type"}
    r = client.options("/execute", headers=pre)
    assert r.status_code == 200 and r.headers.get("access-control-allow-origin") == local
    assert "authorization" in r.headers.get("access-control-allow-headers", "").lower()


# ---------- WebSocket ----------

def test_websocket_requires_key_in_subprotocol(keys):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/signals", headers={"origin": PANEL}) as ws:
            ws.receive_text()
    assert exc.value.code == 1008
    with client.websocket_connect("/ws/signals", headers={"origin": PANEL}, subprotocols=["bearer", READ]) as ws:
        assert ws.accepted_subprotocol == "bearer"


def test_websocket_with_wrong_key_is_closed(keys):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/signals", headers={"origin": PANEL},
                                      subprotocols=["bearer", "x" * 43]) as ws:
            ws.receive_text()
    assert exc.value.code == 1008
