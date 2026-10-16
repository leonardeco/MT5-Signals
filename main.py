import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import math
import os
import time
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd
import numpy as np
import MetaTrader5 as mt5

from signal_engine import QuantSignalEngine, resolve_symbol, EMA_WARMUP_BARS
from execution import requested_price, send_plan_orders
from journal import journal_stats
import backtest
import forward
from risk_guardian import DailyKillSwitch
from news_filter import MarketEnvironmentFilter
from quant_bot_copilot import QuantBotCopilot
from database import (
    init_db, SessionLocal, TradeRecord, KillSwitchEvent,
    log_strong_signal_if_new, sync_open_trades_with_mt5_history
)

WATCHLIST = ["XAUUSD", "EURUSD", "GBPUSD", "US100", "USDJPY"]
MAGIC_NUMBER = 202605
auto_trading_enabled = False
AUTO_TRADE_RETRY_SECONDS = 120
backtest_results = backtest.load_results()
backtest_running = False
auto_trade_cooldown: dict[str, float] = {}
latest_market: dict = {}

engine = QuantSignalEngine(risk_percent=1.0)
kill_switch = DailyKillSwitch(max_daily_loss_pct=3.0, magic=MAGIC_NUMBER)
env_filter = MarketEnvironmentFilter()
bot_copilot = QuantBotCopilot()

# In-memory Demo/Simulation state for when MT5 is offline
simulated_account = {
    "balance": 100000.0,
    "equity": 100000.0,
    "profit": 0.0,
    "margin": 0.0,
    "free_margin": 100000.0,
}
simulated_positions: list[dict] = []
next_virtual_ticket = 910401

BASE_PRICES = {
    "XAUUSD": 2654.50,
    "EURUSD": 1.08720,
    "GBPUSD": 1.29850,
    "US100": 20240.00,
    "USDJPY": 152.650,
}

VOLATILITY = {
    "XAUUSD": 0.85,
    "EURUSD": 0.00018,
    "GBPUSD": 0.00022,
    "US100": 8.50,
    "USDJPY": 0.055,
}

DECIMALS = {
    "XAUUSD": 2,
    "EURUSD": 5,
    "GBPUSD": 5,
    "US100": 2,
    "USDJPY": 3,
}

TF_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}

CONTRACT_MULTIPLIERS = {
    "XAUUSD": 100.0,
    "EURUSD": 100000.0,
    "GBPUSD": 100000.0,
    "US100": 20.0,
    "USDJPY": 1000.0,
}

MT5_PATH = os.environ.get("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

mt5_status_message = ""

def describe_mt5_error(err) -> str:
    code = err[0] if err else 0
    if not os.path.exists(MT5_PATH):
        return f"MetaTrader 5 no está instalado en {MT5_PATH}"
    if code == -6:
        return "MT5 está abierto pero sin sesión: inicia sesión en tu cuenta (Archivo → Conectarse a una cuenta de trading)"
    if code == -10003:
        return "No se pudo abrir la terminal MetaTrader 5"
    if code == -10005:
        return "MT5 tardó demasiado en responder; se reintentará"
    return f"MT5 no disponible ({err})"

def mt5_initialize() -> bool:
    """Conecta con la terminal indicando la ruta: sin ella la librería no la encuentra (error -10003)."""
    global mt5_status_message
    try:
        ok = bool(mt5.initialize(path=MT5_PATH)) if os.path.exists(MT5_PATH) else bool(mt5.initialize())
        mt5_status_message = "" if ok else describe_mt5_error(mt5.last_error())
        return ok
    except Exception as e:
        mt5_status_message = f"Error al conectar con MT5: {e}"
        return False

def offline_signal(symbol: str) -> dict:
    """Placeholder no operable: sin precios reales de MT5 no se emiten BUY/SELL."""
    return {
        "symbol": symbol,
        "direction": "NEUTRAL",
        "score": 0,
        "quality": "WAIT",
        "entry_price": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "recommended_lot": 0.0,
        "rr_ratio": 0.0,
        "atr": 0.0,
        "spread_points": 0,
        "reasons": ["⛔ MT5 desconectado: sin precios reales no hay señal. Abre MetaTrader 5 e inicia sesión."],
        "bot_approved": False,
        "data_source": "OFFLINE",
    }

def is_mt5_live() -> bool:
    try:
        term = mt5.terminal_info()
        return bool(term and term.connected)
    except Exception:
        return False

def get_simulated_dataframe(symbol: str, tf_str: str = "M15", bars: int = 300) -> pd.DataFrame:
    interval = TF_SECONDS.get(tf_str.upper(), 900)
    now_ts = int(time.time())
    current_bar_ts = (now_ts // interval) * interval

    base_price = BASE_PRICES.get(symbol, 100.0)
    vol = VOLATILITY.get(symbol, 0.5)
    decimals = DECIMALS.get(symbol, 2)

    # Deterministic seed per symbol and bar offset to maintain continuous smooth chart
    np.random.seed(abs(hash(symbol)) % 100000)
    steps = np.random.normal(0, vol, bars)
    trend = np.linspace(-vol * 4, vol * 6, bars)
    closes = base_price + np.cumsum(steps) + trend

    data = []
    start_ts = current_bar_ts - (bars - 1) * interval
    for i in range(bars):
        c_bar_ts = start_ts + i * interval
        close_p = round(float(closes[i]), decimals)
        prev_c = round(float(closes[i-1]), decimals) if i > 0 else close_p
        open_p = prev_c
        w_vol = abs(float(np.random.uniform(0.1, 1.2) * vol))
        high_p = round(max(open_p, close_p) + w_vol, decimals)
        low_p = round(min(open_p, close_p) - w_vol, decimals)
        vol_val = int(np.random.randint(120, 850))
        data.append({
            "time": c_bar_ts,
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "tick_volume": vol_val
        })
    df = pd.DataFrame(data)
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    return df

def get_simulated_tick(symbol: str) -> tuple[float, float]:
    df = get_simulated_dataframe(symbol, "M15", 10)
    last = df.iloc[-1]
    vol = VOLATILITY.get(symbol, 0.5)
    decimals = DECIMALS.get(symbol, 2)
    spread = vol * 0.25
    bid = round(float(last["close"]), decimals)
    ask = round(bid + spread, decimals)
    return bid, ask

class ActiveClients:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def broadcast(self, payload: dict):
        for conn in list(self.connections):
            try:
                await conn.send_json(payload)
            except Exception:
                if conn in self.connections:
                    self.connections.remove(conn)

clients = ActiveClients()

def get_filling_mode(symbol: str) -> int:
    try:
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            return mt5.ORDER_FILLING_IOC
        if sym_info.filling_mode & 2:
            return mt5.ORDER_FILLING_IOC
        elif sym_info.filling_mode & 1:
            return mt5.ORDER_FILLING_FOK
        return mt5.ORDER_FILLING_RETURN
    except Exception:
        return 1

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}

def build_chart_dataframe(symbol: str, tf_str: str = "M15", bars: int = 300) -> pd.DataFrame:
    if is_mt5_live():
        tf = TIMEFRAME_MAP.get(tf_str.upper(), mt5.TIMEFRAME_M15)
        try:
            broker_symbol = resolve_symbol(symbol)
            rates = mt5.copy_rates_from_pos(broker_symbol, tf, 0, bars + EMA_WARMUP_BARS) if broker_symbol else None
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
                df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
                df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
                return df.tail(bars).reset_index(drop=True)
        except Exception as e:
            print(f"[Chart Error] {symbol}: {e}")

    # Seamless Simulation/Demo Fallback
    return get_simulated_dataframe(symbol, tf_str, bars)

def cap_volume(requested: float, max_lot: float, min_lot_exceeds_risk: bool, risk_pct: float) -> tuple[Optional[float], Optional[str]]:
    """Nunca aumenta el volumen: lo recorta al lote que arriesga como máximo risk_pct, o rechaza (None, motivo)."""
    if requested <= 0:
        return None, "El volumen debe ser mayor que 0"
    if min_lot_exceeds_risk:
        return None, f"Hasta el lote mínimo arriesga más del {risk_pct}% de la cuenta con este stop"
    if requested > max_lot + 1e-9:
        return max_lot, f"Volumen reducido de {requested} a {max_lot} L para no arriesgar más del {risk_pct}%"
    return requested, None


def risk_capped_volume(symbol: str, broker_symbol: str, direction: str, requested: float, sl: float):
    """Recalcula en el servidor, con el precio actual, el lote máximo para el stop pedido."""
    tick = mt5.symbol_info_tick(broker_symbol)
    if not tick or tick.bid <= 0:
        return None, "Sin cotización para calcular el riesgo"
    price = tick.ask if direction.upper() == "BUY" else tick.bid
    spread = max(0.0, tick.ask - tick.bid)
    # El SL se activa con el precio contrario: la pérdida real incluye el spread (igual que la señal)
    max_lot, exceeds = engine.calculate_lot_size(symbol, abs(price - sl) + spread, price=tick.ask)
    return cap_volume(requested, max_lot, exceeds, engine.risk_percent)


def open_plan(db, symbol: str, broker_symbol: str, direction: str, volume: float, sl: float,
              tp1: Optional[float], tp2: float, score: Optional[int], comment: str):
    """Envía el plan (dos patas TP1/TP2 si se puede) y registra cada pata en la bitácora. Devuelve (patas, error)."""
    legs, err = send_plan_orders(broker_symbol, direction, volume, sl, tp1, tp2, MAGIC_NUMBER, comment)
    group = legs[0][0].order if len(legs) > 1 or (legs and legs[0][2] == "TP1") else None
    for result, vol, leg in legs:
        db.add(TradeRecord(
            ticket=result.order,
            symbol=symbol,
            direction=direction.upper(),
            volume_initial=vol,
            entry_price=result.price,
            requested_price=requested_price(result),
            sl_initial=sl,
            tp_initial=tp1 if leg == "TP1" else tp2,
            # Solo la orden única necesita que la app haga el parcial en TP1; las patas lo tienen en el broker
            tp1=tp1 if leg == "UNICA" else None,
            signal_score=score,
            group_id=group,
            leg=leg,
            status="OPEN",
        ))
    if legs:
        db.commit()
    return legs, err


async def market_scanner_loop():
    global auto_trading_enabled, next_virtual_ticket, latest_market
    last_mt5_reconnect_check = 0.0

    while True:
        try:
            now_ts = time.time()
            # Periodic MT5 auto-connect attempt if offline
            if not is_mt5_live() and (now_ts - last_mt5_reconnect_check) > 5.0:
                last_mt5_reconnect_check = now_ts
                try:
                    if mt5_initialize():
                        if is_mt5_live():
                            bot_copilot.log_event("🟢 Terminal MetaTrader 5 conectado con éxito. Modo LIVE Broker activado.", "SYSTEM")
                except Exception:
                    pass

            live_mode = is_mt5_live()
            was_locked = kill_switch.state.get("locked", False)

            if live_mode:
                risk_status = kill_switch.check_account_safety()
            else:
                sim_profit = sum(p["profit"] for p in simulated_positions)
                sim_equity = simulated_account["balance"] + sim_profit
                sim_pnl_pct = (sim_profit / simulated_account["balance"]) * 100.0 if simulated_account["balance"] > 0 else 0.0
                if not kill_switch.state.get("locked", False) and sim_pnl_pct <= -abs(kill_switch.max_daily_loss_pct):
                    kill_switch.state["locked"] = True
                    kill_switch.state["lock_reason"] = (
                        f"🚨 KILL SWITCH ACTIVADO (Demo): Pérdida {sim_pnl_pct:.2f}% superó el límite ({kill_switch.max_daily_loss_pct}%)."
                    )
                    simulated_positions.clear()
                risk_status = {
                    "locked": kill_switch.state.get("locked", False),
                    "starting_balance": round(simulated_account["balance"], 2),
                    "current_equity": round(sim_equity, 2),
                    "current_balance": round(simulated_account["balance"], 2),
                    "daily_pnl": round(sim_profit, 2),
                    "daily_pnl_pct": round(sim_pnl_pct, 2),
                    "lock_reason": kill_switch.state.get("lock_reason", ""),
                    "max_daily_loss_pct": kill_switch.max_daily_loss_pct
                }

            with SessionLocal() as db:
                if not was_locked and risk_status["locked"]:
                    db.add(KillSwitchEvent(
                        starting_balance=risk_status["starting_balance"],
                        trigger_equity=risk_status["current_equity"],
                        daily_loss_pct=risk_status["daily_pnl_pct"],
                        reason=risk_status["lock_reason"]
                    ))
                    db.commit()
                    auto_trading_enabled = False
                    bot_copilot.log_event("🚨 Kill Switch Bloqueó el Trading Automático.", "CRITICAL")

                if live_mode:
                    sync_open_trades_with_mt5_history(db)
                    if not risk_status["locked"]:
                        trade_meta = {
                            t.ticket: {
                                "risk": abs(t.entry_price - t.sl_initial) if t.entry_price and t.sl_initial else None,
                                "tp1": t.tp1,
                                "volume_initial": t.volume_initial,
                                "leg": t.leg,
                                "group_id": t.group_id,
                            }
                            for t in db.query(TradeRecord).filter(TradeRecord.status == "OPEN").all()
                        }
                        bot_copilot.manage_smart_trailing_and_partials(MAGIC_NUMBER, get_filling_mode, trade_meta)
                else:
                    # Update simulated positions prices and trailing in demo
                    for pos in simulated_positions:
                        bid, ask = get_simulated_tick(pos["symbol"])
                        cur_p = bid if pos["type"] == "BUY" else ask
                        pos["price_current"] = cur_p
                        mult = CONTRACT_MULTIPLIERS.get(pos["symbol"], 100.0)
                        diff = (cur_p - pos["price_open"]) if pos["type"] == "BUY" else (pos["price_open"] - cur_p)
                        pos["profit"] = round(diff * pos["volume"] * mult, 2)
                        # Breakeven condition
                        if pos["type"] == "BUY" and pos["sl"] >= pos["price_open"]:
                            pos["is_breakeven"] = True
                        elif pos["type"] == "SELL" and pos["sl"] <= pos["price_open"] and pos["sl"] > 0:
                            pos["is_breakeven"] = True

                signals = []
                active_symbols = set()
                if live_mode:
                    try:
                        positions_raw = mt5.positions_get() or []
                        broker_to_watch = {resolve_symbol(w): w for w in WATCHLIST}
                        active_symbols = {broker_to_watch.get(p.symbol, p.symbol) for p in positions_raw}
                    except Exception:
                        positions_raw = []
                else:
                    active_symbols = {p["symbol"] for p in simulated_positions}

                for sym in WATCHLIST:
                    if not live_mode:
                        # Sin MT5 solo hay velas aleatorias: nunca generar, registrar ni auto-ejecutar señales con ellas
                        signals.append(offline_signal(sym))
                        continue

                    res = engine.evaluate_symbol(sym)
                    if res:
                        df_m15 = engine._fetch_df(res["broker_symbol"], mt5.TIMEFRAME_M15, 20)
                        res = bot_copilot.enrich_signal_with_bot_telemetry(res, df_m15)
                        res["history"] = history_for(sym, res["score"])
                        res["auto_eligible"] = history_allows_auto(res["history"])

                    if res:
                        env = env_filter.evaluate_environment(sym)
                        res["environment"] = env
                        if env["news_blocked"]:
                            res["reasons"].append(f"⚠️ {env['news_message']}")
                        if not env["session_ok"]:
                            res["reasons"].append("🕒 Fuera de horario operativo de alta volatilidad")

                        log_strong_signal_if_new(db, res)
                        signals.append(res)

                        # Ejecución automática si cumple todas las reglas institucionales
                        if (
                            auto_trading_enabled
                            and not risk_status["locked"]
                            and env["allowed"]
                            and res["bot_approved"]
                            and res.get("executable")
                            and history_allows_auto(res.get("history"))
                            and sym not in active_symbols
                            and time.time() >= auto_trade_cooldown.get(sym, 0.0)
                        ):
                            capped, cap_msg = risk_capped_volume(
                                sym, res["broker_symbol"], res["direction"], res["recommended_lot"], res["sl"]
                            )
                            if capped is None:
                                legs, err = [], cap_msg
                            else:
                                legs, err = open_plan(
                                    db, sym, res["broker_symbol"], res["direction"], capped, res["sl"],
                                    res.get("tp1"), res["tp"], res["score"], f"QuantBot {res['score']}"
                                )
                            if legs:
                                active_symbols.add(sym)
                                desc = " + ".join(f"#{r.order} {vol} L ({leg})" for r, vol, leg in legs)
                                bot_copilot.log_event(
                                    f"🚀 LIVE {res['direction']} {sym} @ {legs[0][0].price}: {desc}"
                                    + (f" · ⚠️ {err}" if err else ""),
                                    "EXECUTION"
                                )
                            else:
                                # Sin enfriamiento reintentaría la misma orden rechazada cada 1.5 s
                                auto_trade_cooldown[sym] = time.time() + AUTO_TRADE_RETRY_SECONDS
                                bot_copilot.log_event(f"⛔ Auto-trade {sym} no enviado: {err}", "CRITICAL")

            # Prepare telemetry payload
            positions_data = []
            if live_mode:
                acc = mt5.account_info()
                account_payload = {
                    "balance": round(acc.balance, 2) if acc else 0,
                    "equity": round(acc.equity, 2) if acc else 0,
                    "profit": round(acc.profit, 2) if acc else 0,
                    "margin": round(acc.margin, 2) if acc else 0,
                    "free_margin": round(acc.margin_free, 2) if acc else 0
                } if acc else {}
                for p in mt5.positions_get() or []:
                    is_be = (p.type == 0 and p.sl >= p.price_open) or (p.type == 1 and p.sl <= p.price_open and p.sl > 0)
                    positions_data.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "type": "BUY" if p.type == 0 else "SELL",
                        "volume": p.volume,
                        "price_open": p.price_open,
                        "price_current": p.price_current,
                        "sl": p.sl,
                        "tp": p.tp,
                        "profit": round(p.profit + p.swap, 2),
                        "is_breakeven": is_be
                    })
            else:
                sim_profit = sum(p["profit"] for p in simulated_positions)
                account_payload = {
                    "balance": round(simulated_account["balance"], 2),
                    "equity": round(simulated_account["balance"] + sim_profit, 2),
                    "profit": round(sim_profit, 2),
                    "margin": round(sum(p["volume"] * 1000 for p in simulated_positions), 2),
                    "free_margin": round(simulated_account["balance"] + sim_profit - sum(p["volume"] * 1000 for p in simulated_positions), 2)
                }
                positions_data = list(simulated_positions)

            latest_market = {
                "type": "MARKET_UPDATE",
                "mt5_connected": live_mode,
                "mt5_status": "" if live_mode else (mt5_status_message or "Esperando a MetaTrader 5..."),
                "account": account_payload,
                "risk": risk_status,
                "autotrading": auto_trading_enabled,
                "bot_logs": bot_copilot.activity_logs,
                "bot_mode": bot_copilot.mode,
                "signals": sorted(signals, key=lambda x: x["score"], reverse=True),
                "positions": positions_data
            }
            await clients.broadcast(latest_market)
        except Exception as e:
            print(f"[Scanner Error]: {e}")

        await asyncio.sleep(1.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mt5_ok = mt5_initialize()
    if not mt5_ok:
        print(f"[MT5 Info]: MT5 terminal no detectado aún ({mt5.last_error()}). Servidor activo en Modo Simulación.")
        bot_copilot.log_event("🟡 Servidor activo en Modo Demostración Cuantitativa (MT5 desconectado).", "INFO")
    else:
        print("[MT5 Success]: Conectado a terminal de MetaTrader 5.")
        bot_copilot.log_event("🟢 Terminal MetaTrader 5 conectado con éxito.", "SYSTEM")

    scanner_task = asyncio.create_task(market_scanner_loop())
    yield
    scanner_task.cancel()
    try:
        mt5.shutdown()
    except Exception:
        pass

app = FastAPI(title="MT5 Quant Pro API", lifespan=lifespan)

# Solo el frontend local puede hablar con la API. Con "*" cualquier web abierta en el navegador podía
# leer la cuenta por WebSocket o lanzar POST /execute, /close-all... contra 127.0.0.1:8000.
def _origins_from_file() -> set[str]:
    """Orígenes extra (por ejemplo la URL de Vercel) sin meterlos en el código."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "allowed_origins.local")
    found: set[str] = set()
    if not os.path.isfile(path):
        return found
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if line:
                found.add(line)
    return found


ALLOWED_ORIGINS = {
    o.strip() for o in os.environ.get(
        "QUANT_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",") if o.strip()
} | _origins_from_file()

def origin_allowed(origin: Optional[str]) -> bool:
    """Sin cabecera Origin (curl, scripts locales) se permite; un navegador siempre la envía en peticiones cruzadas."""
    return origin is None or origin in ALLOWED_ORIGINS

@app.middleware("http")
async def reject_foreign_origins(request, call_next):
    # CORS no frena los POST "simples" (sin cuerpo JSON): el navegador los envía igual y solo oculta la respuesta
    if request.method not in ("GET", "HEAD", "OPTIONS") and not origin_allowed(request.headers.get("origin")):
        return JSONResponse(status_code=403, content={"detail": "Origen no permitido"})
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def allow_private_network(request, call_next):
    """Chrome pide este encabezado cuando un panel https (Vercel) llama a 127.0.0.1."""
    response = await call_next(request)
    asks = request.headers.get("access-control-request-private-network") == "true"
    if asks and origin_allowed(request.headers.get("origin")):
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

class ExecuteSignalRequest(BaseModel):
    symbol: str
    direction: str
    volume: float
    sl: float
    tp: float
    tp1: Optional[float] = None
    score: Optional[int] = None

class ModeRequest(BaseModel):
    mode: str

class AutoTradingRequest(BaseModel):
    enabled: bool

@app.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket):
    if not origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    clients.connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in clients.connections:
            clients.connections.remove(websocket)

@app.websocket("/ws/chart/{symbol}")
async def websocket_live_chart(websocket: WebSocket, symbol: str, tf: str = "M15"):
    if not origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            df = build_chart_dataframe(symbol, tf, bars=210)
            if df is not None and len(df) > 0:
                last = df.iloc[-1]
                t = int(last["time"])
                close_p = float(last["close"])
                high_p = float(last["high"])
                low_p = float(last["low"])

                # In offline demo mode, inject realistic micro-tick movements
                if not is_mt5_live():
                    vol = VOLATILITY.get(symbol, 0.5)
                    decimals = DECIMALS.get(symbol, 2)
                    micro = round(float(np.random.normal(0, vol * 0.12)), decimals)
                    close_p = round(close_p + micro, decimals)
                    high_p = max(high_p, close_p)
                    low_p = min(low_p, close_p)

                await websocket.send_json({
                    "type": "TICK_BAR",
                    "simulated": not is_mt5_live(),
                    "candle": {
                        "time": t,
                        "open": float(last["open"]),
                        "high": high_p,
                        "low": low_p,
                        "close": close_p,
                    },
                    "ema21": {"time": t, "value": float(last["ema21"])},
                    "ema50": {"time": t, "value": float(last["ema50"])},
                    "ema200": {"time": t, "value": float(last["ema200"])},
                })
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass

@app.get("/candles/{symbol}")
def get_historical_candles(
    symbol: str,
    tf: str = Query("M15", description="M1, M5, M15, H1, H4, D1"),
    bars: int = Query(300, ge=50, le=1500)
):
    df = build_chart_dataframe(symbol, tf, bars)
    if df is None or len(df) == 0:
        raise HTTPException(status_code=404, detail=f"Sin datos para {symbol}")

    candles = []
    ema21_data = []
    ema50_data = []
    ema200_data = []

    for row in df.itertuples():
        t = int(row.time)
        candles.append({
            "time": t,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        })
        ema21_data.append({"time": t, "value": float(row.ema21)})
        ema50_data.append({"time": t, "value": float(row.ema50)})
        ema200_data.append({"time": t, "value": float(row.ema200)})

    return {
        "symbol": symbol,
        "timeframe": tf,
        "simulated": not is_mt5_live(),
        "candles": candles,
        "ema21": ema21_data,
        "ema50": ema50_data,
        "ema200": ema200_data,
    }

@app.post("/execute")
def execute_trade(req: ExecuteSignalRequest):
    global next_virtual_ticket
    live = is_mt5_live()

    if not live:
        # Sin MT5 los precios son aleatorios: no abrir posiciones con ellos
        raise HTTPException(status_code=503, detail="MT5 desconectado: no se ejecutan órdenes con precios simulados")
    if kill_switch.state.get("locked", False):
        raise HTTPException(status_code=403, detail="Kill Switch activo: trading bloqueado por pérdida diaria")

    broker_symbol = resolve_symbol(req.symbol)
    if not broker_symbol:
        raise HTTPException(status_code=400, detail=f"{req.symbol} no existe en tu broker")

    capped, cap_msg = risk_capped_volume(req.symbol, broker_symbol, req.direction, req.volume, req.sl)
    if capped is None:
        raise HTTPException(status_code=400, detail=f"Orden no enviada: {cap_msg}")

    with SessionLocal() as db:
        legs, err = open_plan(db, req.symbol, broker_symbol, req.direction, capped, req.sl, req.tp1, req.tp,
                              req.score, "QuantApp Signal")
    if not legs:
        raise HTTPException(status_code=400, detail=f"Orden no enviada: {err}")

    first = legs[0][0]
    ticket, executed_price = first.order, first.price
    volume = round(sum(vol for _, vol, _ in legs), 2)
    notes = [n for n in (cap_msg, err) if n]
    if len(legs) == 2:
        notes.append("dividida en dos órdenes: la mitad cierra sola en TP1 en el broker")
    note = " · ".join(notes) or None

    bot_copilot.log_event(
        f"⚡ Manual: {req.direction.upper()} {volume} en {req.symbol} @ {executed_price} "
        f"(Tickets {', '.join('#' + str(r.order) for r, _, _ in legs)})" + (f" · {note}" if note else ""),
        "TRADE"
    )

    return {
        "status": "ok",
        "ticket": ticket,
        "tickets": [r.order for r, _, _ in legs],
        "executed_price": executed_price,
        "volume": volume,
        "risk_note": note,
        "mode": "LIVE" if live else "DEMO"
    }

@app.post("/close/{ticket}")
def close_single_position(ticket: int):
    live = is_mt5_live()

    if live:
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            raise HTTPException(status_code=404, detail="Posición no encontrada en MT5")
        
        pos = positions[0]
        sym_info = mt5.symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        if not sym_info or not tick:
            raise HTTPException(status_code=400, detail="Error de símbolo")

        is_buy = (pos.type == mt5.POSITION_TYPE_BUY)
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 25,
            "magic": pos.magic,
            "comment": "Manual Close UI",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": get_filling_mode(pos.symbol)
        }
        r = mt5.order_send(req)
        if not r or r.retcode != mt5.TRADE_RETCODE_DONE:
            err = r.comment if r else mt5.last_error()
            raise HTTPException(status_code=400, detail=f"No se pudo cerrar: {err}")

        bot_copilot.log_event(f"❌ Posición LIVE #{pos.ticket} ({pos.symbol}) cerrada.", "INFO")
        return {"status": "closed", "ticket": ticket}
    else:
        # Close from simulated positions
        pos = next((p for p in simulated_positions if p["ticket"] == ticket), None)
        if not pos:
            raise HTTPException(status_code=404, detail="Posición simulada no encontrada")

        simulated_positions.remove(pos)
        simulated_account["balance"] += pos["profit"]
        with SessionLocal() as db:
            trade = db.query(TradeRecord).filter(TradeRecord.ticket == ticket).first()
            if trade:
                trade.status = "CLOSED"
                trade.profit = pos["profit"]
                trade.close_price = pos["price_current"]
                trade.close_time = datetime.utcnow()
                db.commit()

        bot_copilot.log_event(f"❌ Posición DEMO #{ticket} ({pos['symbol']}) cerrada con PnL: ${pos['profit']}.", "INFO")
        return {"status": "closed", "ticket": ticket, "profit": pos["profit"]}

@app.post("/close-all")
def close_all():
    closed = 0
    if is_mt5_live():
        closed = kill_switch.emergency_close_all()
    else:
        closed = len(simulated_positions)
        total_pnl = sum(p["profit"] for p in simulated_positions)
        simulated_account["balance"] += total_pnl
        with SessionLocal() as db:
            for pos in simulated_positions:
                trade = db.query(TradeRecord).filter(TradeRecord.ticket == pos["ticket"]).first()
                if trade:
                    trade.status = "CLOSED"
                    trade.profit = pos["profit"]
                    trade.close_price = pos["price_current"]
                    trade.close_time = datetime.utcnow()
            db.commit()
        simulated_positions.clear()

    bot_copilot.log_event(f"🚨 Cierre de emergencia ejecutado: {closed} posiciones del bot liquidadas.", "CRITICAL")
    return {"status": "ok", "closed_positions": closed}

@app.post("/bot/mode")
def change_bot_mode(req: ModeRequest):
    res = bot_copilot.set_mode(req.mode)
    return res

@app.post("/bot/autotrading")
def toggle_autotrading(req: AutoTradingRequest):
    global auto_trading_enabled
    if kill_switch.state.get("locked", False) and req.enabled:
        raise HTTPException(status_code=400, detail="No se puede habilitar: Kill Switch está activo")
    auto_trading_enabled = req.enabled
    bot_copilot.log_event(
        f"🤖 Auto-Trading {'ACTIVADO ✅' if auto_trading_enabled else 'PAUSADO ⏸️'}",
        "SYSTEM"
    )
    return {"autotrading": auto_trading_enabled}

@app.post("/risk/reset")
def reset_risk_lock():
    res = kill_switch.reset_lock()
    bot_copilot.log_event("🛡️ Kill Switch reiniciado manualmente.", "SYSTEM")
    return res

@app.get("/history")
def get_trade_history():
    with SessionLocal() as db:
        trades = db.query(TradeRecord).order_by(TradeRecord.id.desc()).limit(50).all()
        return [
            {
                "id": t.id,
                "ticket": t.ticket,
                "symbol": t.symbol,
                "direction": t.direction,
                "volume": t.volume_initial,
                "entry_price": t.entry_price,
                "sl": t.sl_initial,
                "tp": t.tp_initial,
                "score": t.signal_score,
                "status": t.status,
                "profit": t.profit,
                "close_price": t.close_price,
                "open_time": t.open_time.isoformat() if t.open_time else None,
                "close_time": t.close_time.isoformat() if t.close_time else None,
                "leg": t.leg,
                "group_id": t.group_id,
                "r_multiple": t.r_multiple,
                "mae_r": t.mae_r,
                "mfe_r": t.mfe_r,
                "slippage_px": slippage_px(t),
            }
            for t in trades
        ]


def slippage_px(t) -> Optional[float]:
    """Deslizamiento en contra (> 0) o a favor (< 0) entre el precio pedido y el ejecutado."""
    if t.requested_price is None or t.entry_price is None:
        return None
    diff = t.entry_price - t.requested_price
    return round(diff if t.direction == "BUY" else -diff, 6)


@app.get("/journal/stats")
def get_journal_stats():
    """Expectativa en R de las operaciones cerradas frente a la media neta del backtest de cada símbolo."""
    with SessionLocal() as db:
        rows = db.query(TradeRecord).filter(TradeRecord.status == "CLOSED").all()
        trades = [{"ticket": t.ticket, "symbol": t.symbol, "group_id": t.group_id, "volume": t.volume_initial,
                   "r_multiple": t.r_multiple, "mae_r": t.mae_r, "mfe_r": t.mfe_r, "slippage_px": slippage_px(t)}
                  for t in rows]
    bt = {s: d["nuevo"]["avg_r"] for s, d in ((backtest_results or {}).get("symbols", {})).items() if "nuevo" in d}
    return journal_stats(trades, bt)

def history_for(symbol: str, score: int) -> Optional[dict]:
    """Resultado histórico del plan nuevo para el símbolo y el rango de score de la señal."""
    data = (backtest_results or {}).get("symbols", {}).get(symbol)
    if not data or "nuevo" not in data:
        return None
    nuevo = data["nuevo"]
    bucket = backtest.score_bucket(score)
    b = nuevo.get("by_bucket", {}).get(bucket, {})
    split = nuevo.get("split", {})
    old, recent = split.get("antiguo", {}), split.get("reciente", {})
    return {
        "period": data.get("period"),
        "bucket": bucket,
        "bucket_n": b.get("n", 0),
        "bucket_win_rate": b.get("win_rate", 0.0),
        "bucket_avg_r": b.get("avg_r", 0.0),
        "symbol_n": nuevo.get("n", 0),
        "symbol_win_rate": nuevo.get("win_rate", 0.0),
        "symbol_avg_r": nuevo.get("avg_r", 0.0),
        "symbol_profit_factor": nuevo.get("profit_factor"),
        "symbol_t_stat": nuevo.get("t_stat"),
        "old_n": old.get("n", 0),
        "old_avg_r": old.get("avg_r", 0.0),
        "recent_n": recent.get("n", 0),
        "recent_avg_r": recent.get("avg_r", 0.0),
    }


AUTO_MIN_TRADES = 30      # en cada tramo (antiguo 60% y reciente 40% del periodo)
AUTO_MIN_AVG_R = 0.05     # en cada tramo
AUTO_MIN_T_STAT = 2.0     # sobre el total del periodo

def history_allows_auto(history: Optional[dict]) -> bool:
    """El auto-trading solo opera símbolos cuya ventaja se sostiene en ambos tramos del backtest y es
    estadísticamente distinguible de 0R. Sin datos de tramos o de t (resultados antiguos) no se habilita."""
    if not history:
        return False
    t = history.get("symbol_t_stat")
    return (
        history.get("old_n", 0) >= AUTO_MIN_TRADES
        and history.get("recent_n", 0) >= AUTO_MIN_TRADES
        and history.get("old_avg_r", 0.0) >= AUTO_MIN_AVG_R
        and history.get("recent_avg_r", 0.0) >= AUTO_MIN_AVG_R
        and t is not None
        and t >= AUTO_MIN_T_STAT
    )


@app.get("/backtest")
def get_backtest():
    return {"running": backtest_running, "results": backtest_results}


@app.post("/backtest/run")
async def run_backtest_endpoint(days: int = Query(backtest.DEFAULT_DAYS, ge=30, le=365)):
    global backtest_results, backtest_running
    if not is_mt5_live():
        raise HTTPException(status_code=503, detail="MT5 desconectado: el backtest necesita el historial real")
    if backtest_running:
        raise HTTPException(status_code=409, detail="Ya hay un backtest en curso")
    backtest_running = True
    try:
        # En el hilo del escáner a propósito: evita llamadas simultáneas a MT5 desde dos hilos (pausa ~15 s)
        backtest_results = backtest.run_backtest(WATCHLIST, days)
        bot_copilot.log_event(f"📊 Backtest de {days} días actualizado", "SYSTEM")
        return {"running": False, "results": backtest_results}
    finally:
        backtest_running = False


@app.get("/forward")
def get_forward():
    """Prueba a futuro en sombra (reglas congeladas, sin órdenes): último cálculo guardado."""
    return {"running": backtest_running, "config": forward.load_config(), "results": forward.load_results()}


@app.post("/forward/run")
async def run_forward_endpoint():
    global backtest_running
    if not is_mt5_live():
        raise HTTPException(status_code=503, detail="MT5 desconectado: la prueba a futuro necesita el historial real")
    if forward.load_config() is None:
        raise HTTPException(status_code=409, detail="Las reglas aún no están congeladas (python forward.py freeze)")
    if backtest_running:
        raise HTTPException(status_code=409, detail="Ya hay un cálculo en curso")
    backtest_running = True
    try:
        # Igual que el backtest: en el hilo del escáner para no llamar a MT5 desde dos hilos a la vez
        results = forward.run(mt5)
        bot_copilot.log_event("🧪 Prueba a futuro en sombra actualizada", "SYSTEM")
        return {"running": False, "config": forward.load_config(), "results": results}
    finally:
        backtest_running = False


@app.get("/market")
def get_market():
    """Misma foto que el WebSocket. Sirve si el navegador bloquea ws:// desde una página https."""
    if latest_market:
        return latest_market
    return {
        "type": "MARKET_UPDATE",
        "mt5_connected": is_mt5_live(),
        "mt5_status": "" if is_mt5_live() else (mt5_status_message or "Esperando a MetaTrader 5..."),
        "account": {"balance": 0.0, "equity": 0.0, "profit": 0.0, "margin": 0.0, "free_margin": 0.0},
        "risk": {
            "locked": False,
            "starting_balance": 0.0,
            "current_equity": 0.0,
            "current_balance": 0.0,
            "daily_pnl": 0.0,
            "daily_pnl_pct": 0.0,
            "lock_reason": "",
            "max_daily_loss_pct": kill_switch.max_daily_loss_pct,
        },
        "autotrading": auto_trading_enabled,
        "bot_logs": bot_copilot.activity_logs,
        "bot_mode": bot_copilot.mode,
        "signals": [],
        "positions": [],
    }


@app.get("/status")
def get_status():
    live = is_mt5_live()
    return {
        "status": "online",
        "mt5_connected": live,
        "mode": "LIVE" if live else "DEMO",
        "watchlist": WATCHLIST,
        "magic": MAGIC_NUMBER,
        "autotrading": auto_trading_enabled,
        "bot_mode": bot_copilot.mode,
    }
