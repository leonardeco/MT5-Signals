from datetime import datetime
import math
import MetaTrader5 as mt5
import pandas as pd

class QuantBotCopilot:
    def __init__(self):
        self.mode = "INSTITUTIONAL"
        self.min_score_map = {"SNIPER": 85, "INSTITUTIONAL": 75, "DYNAMIC": 65}
        self.auto_partial_done = set()
        self.activity_logs = []
        self.log_event("🤖 QuantBot Copilot iniciado (Modo INSTITUTIONAL).", "INFO")

    def log_event(self, message: str, level: str = "INFO"):
        now_str = datetime.now().strftime("%H:%M:%S")
        if self.activity_logs and self.activity_logs[0]["message"] == message:
            return
        self.activity_logs.insert(0, {"time": now_str, "message": message, "level": level})
        self.activity_logs = self.activity_logs[:50]

    def set_mode(self, mode: str):
        mode_up = mode.upper()
        if mode_up in self.min_score_map:
            self.mode = mode_up
            self.log_event(f"⚙️ Modo cambiado a {self.mode} (Score >= {self.min_score_map[self.mode]})", "SYSTEM")
        return {"mode": self.mode, "min_score": self.min_score_map.get(self.mode, 75)}

    @staticmethod
    def detect_smc_fvg(df: pd.DataFrame) -> dict:
        if df is None or len(df) < 5:
            return {"bullish_fvg": False, "bearish_fvg": False, "fvg_zone": None}
        c1, c2, c3 = df.iloc[-4], df.iloc[-3], df.iloc[-2]
        bullish = bool(c3["low"] > c1["high"] and c2["close"] > c2["open"])
        bearish = bool(c3["high"] < c1["low"] and c2["close"] < c2["open"])
        zone = None
        if bullish:
            zone = (round(float(c1["high"]), 5), round(float(c3["low"]), 5))
        elif bearish:
            zone = (round(float(c3["high"]), 5), round(float(c1["low"]), 5))
        return {"bullish_fvg": bullish, "bearish_fvg": bearish, "fvg_zone": zone}

    def enrich_signal_with_bot_telemetry(self, sig: dict, df_m15: pd.DataFrame) -> dict:
        smc = self.detect_smc_fvg(df_m15)
        bonus = 0
        if sig["direction"] == "BUY" and smc["bullish_fvg"]:
            bonus = 10
            sig["reasons"].insert(0, f"✨ FVG Institucional Alcista {smc['fvg_zone']}")
        elif sig["direction"] == "SELL" and smc["bearish_fvg"]:
            bonus = 10
            sig["reasons"].insert(0, f"✨ FVG Institucional Bajista {smc['fvg_zone']}")
        
        sig["score"] = min(100, sig["score"] + bonus)
        if bonus and "pillars" in sig:
            sig["pillars"]["smc_liquidity"] = min(25, sig["pillars"]["smc_liquidity"] + bonus)
        min_required = self.min_score_map.get(self.mode, 75)
        sig["bot_approved"] = bool(sig["direction"] != "NEUTRAL" and sig["score"] >= min_required)
        sig["quality"] = "STRONG" if sig["score"] >= 75 else ("MODERATE" if sig["score"] >= 60 else "WAIT")
        if sig["bot_approved"]:
            self.log_event(f"🎯 {sig['symbol']} supera el score mínimo del modo ({sig['direction']} • {sig['score']}/100)", "SIGNAL")
        return sig

    def manage_smart_trailing_and_partials(self, magic_number: int, get_filling_mode_fn, trade_meta: dict | None = None):
        """trade_meta: ticket -> {"risk", "tp1", "volume_initial"} desde la bitácora.

        Con TP1 (plan nuevo): cierra 50% en TP1 y mueve el stop a breakeven, igual que el backtest.
        Sin TP1 (operaciones antiguas): parcial en +1.5R y trailing por ATR.
        """
        positions = mt5.positions_get(magic=magic_number)
        if not positions:
            return
        open_tickets = {p.ticket for p in positions}
        for pos in positions:
            if pos.sl == 0.0:
                continue
            meta = (trade_meta or {}).get(pos.ticket, {})
            if meta.get("leg") == "TP1":
                continue  # su TP la cierra el broker
            if meta.get("leg") == "TP2":
                self._breakeven_after_tp1_leg(pos, meta, open_tickets)
                continue
            sym = mt5.symbol_info(pos.symbol)
            tick = mt5.symbol_info_tick(pos.symbol)
            rates = mt5.copy_rates_from_pos(pos.symbol, mt5.TIMEFRAME_M15, 0, 20)
            if not sym or not tick or rates is None:
                continue

            df = pd.DataFrame(rates)
            atr = float((df["high"] - df["low"]).tail(14).mean())
            if atr <= 0:
                atr = sym.point * 15
            is_buy = (pos.type == mt5.POSITION_TYPE_BUY)
            tp1 = meta.get("tp1")

            # Riesgo inicial real (entrada - SL original de la bitácora); el ATR actual es solo respaldo
            init_risk = meta.get("risk") or max(atr * 1.5, sym.point * 10)
            gain = (pos.price_current - pos.price_open) if is_buy else (pos.price_open - pos.price_current)
            r_mult = gain / init_risk if init_risk > 0 else 0.0
            # Tras un reinicio, un volumen menor al inicial indica que el parcial ya se hizo
            vol_init = meta.get("volume_initial") or pos.volume
            partial_done = pos.ticket in self.auto_partial_done or pos.volume < vol_init - 1e-9

            if tp1:
                reached = (tick.bid >= tp1) if is_buy else (tick.ask <= tp1)
                if reached and not partial_done:
                    if self._close_partial(pos, sym, tick, is_buy, magic_number, get_filling_mode_fn, "TP1"):
                        partial_done = True
                if partial_done:
                    be = round(pos.price_open, sym.digits)
                    needs_be = (is_buy and pos.sl < be) or (not is_buy and pos.sl > be)
                    if needs_be:
                        r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket,
                                            "symbol": pos.symbol, "sl": be, "tp": pos.tp})
                        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                            self.log_event(f"🛡️ #{pos.ticket}: stop a breakeven tras TP1", "PROFIT")
                continue

            # Operaciones sin TP1: parcial 50% al alcanzar +1.5R
            if r_mult >= 1.5 and not partial_done:
                self._close_partial(pos, sym, tick, is_buy, magic_number, get_filling_mode_fn, "+1.5R")

            # Trailing stop inteligente dinámico
            if r_mult >= 1.5:
                trail = atr * 1.2
                proposed_sl = round(pos.price_current - trail if is_buy else pos.price_current + trail, sym.digits)
                if (is_buy and proposed_sl > pos.sl and proposed_sl > pos.price_open) or (not is_buy and proposed_sl < pos.sl and proposed_sl < pos.price_open):
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "symbol": pos.symbol,
                        "sl": proposed_sl,
                        "tp": pos.tp
                    })

    def _breakeven_after_tp1_leg(self, pos, meta: dict, open_tickets: set) -> bool:
        """Pata TP2 de una orden dividida: cuando la pata TP1 ya no está abierta y la posición va en
        beneficio, el stop pasa a breakeven (como en el backtest: 50 % en TP1 y resto a breakeven)."""
        sibling = meta.get("group_id")
        if not sibling or sibling in open_tickets:
            return False
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        in_profit = pos.price_current > pos.price_open if is_buy else pos.price_current < pos.price_open
        already = pos.sl >= pos.price_open if is_buy else (0 < pos.sl <= pos.price_open)
        if not in_profit or already:
            return False
        sym = mt5.symbol_info(pos.symbol)
        be = round(pos.price_open, sym.digits) if sym else pos.price_open
        r = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket,
                            "symbol": pos.symbol, "sl": be, "tp": pos.tp})
        if r and r.retcode == mt5.TRADE_RETCODE_DONE:
            self.log_event(f"🛡️ #{pos.ticket}: stop a breakeven (la pata TP1 #{sibling} ya cerró)", "PROFIT")
            return True
        return False

    def _close_partial(self, pos, sym, tick, is_buy, magic_number, get_filling_mode_fn, label: str) -> bool:
        if pos.volume < sym.volume_min * 2:
            return False
        close_vol = round(math.floor((pos.volume * 0.5) / sym.volume_step) * sym.volume_step, 2)
        if close_vol < sym.volume_min:
            return False
        filling = get_filling_mode_fn(pos.symbol) if callable(get_filling_mode_fn) else mt5.ORDER_FILLING_IOC
        res = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "position": pos.ticket,
            "symbol": pos.symbol,
            "volume": close_vol,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": magic_number,
            "comment": f"Bot Partial 50% {label}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling
        })
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            self.auto_partial_done.add(pos.ticket)
            self.log_event(f"💰 Parcial 50% en #{pos.ticket} ({label})", "PROFIT")
            return True
        return False
