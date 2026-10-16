
import time

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import Optional

from setups import (
    SetupTracker, build_plan, collect_levels, m5_trigger, recent_fvg,
    ACTIVADA, EN_ZONA, SIN_SETUP,
)

# Nombres alternativos que usan los brokers para el mismo instrumento
SYMBOL_ALIASES = {
    "US100": ["US100", "NAS100", "USTEC", "NDX100", "NQ100", "US100Cash"],
    "XAUUSD": ["XAUUSD", "GOLD"],
}
_resolved_symbols: dict[str, str] = {}

# Barras extra para que la EMA 200 converja igual que en MT5 (adjust=False arrastra la semilla inicial)
EMA_WARMUP_BARS = 800


def resolve_symbol(symbol: str) -> Optional[str]:
    """Devuelve el nombre real del símbolo en el broker (p. ej. 'USDJPY.m', 'NAS100') o None."""
    if symbol in _resolved_symbols:
        return _resolved_symbols[symbol]
    candidates = SYMBOL_ALIASES.get(symbol, [symbol])
    found = None
    for cand in candidates:
        if mt5.symbol_info(cand):
            found = cand
            break
    if not found:
        all_names = [s.name for s in (mt5.symbols_get() or [])]
        for cand in candidates:
            # Sufijos típicos: USDJPY.m, USDJPYm, USDJPY.raw, US100.cash
            matches = [n for n in all_names if n.upper().startswith(cand.upper()) and len(n) <= len(cand) + 5]
            if matches:
                found = min(matches, key=len)
                break
    if found:
        mt5.symbol_select(found, True)
        _resolved_symbols[symbol] = found
    return found


MIN_SIGNAL_SCORE = 55


def _num(row, key, default=0.0) -> float:
    v = row[key]
    return default if v is None or pd.isna(v) else float(v)


def score_bar(curr, prev, h1_curr, spread_price: float, atr: float, digits: int) -> dict:
    """Puntúa la última vela M15 cerrada (curr) con su vela previa y la última H1 cerrada.

    Acepta filas de pandas o diccionarios; la usan el escáner en vivo y el backtest.
    """
    buy_p = {"macro_h1": 0, "structure_m15": 0, "smc_liquidity": 0, "momentum": 0, "execution_cost": 0}
    sell_p = dict(buy_p)
    buy_reasons, sell_reasons = [], []

    # 1. Macro Trend H1 (25)
    if h1_curr['close'] > h1_curr['ema200'] and h1_curr['ema50'] > h1_curr['ema200']:
        buy_p["macro_h1"] = 25
        buy_reasons.append("Tendencia alcista H1 (EMA 50/200)")
    elif h1_curr['close'] < h1_curr['ema200'] and h1_curr['ema50'] < h1_curr['ema200']:
        sell_p["macro_h1"] = 25
        sell_reasons.append("Tendencia bajista H1 (EMA 50/200)")

    # 2. Value zone pullback M15 (25)
    if curr['close'] > curr['ema50'] and curr['low'] <= curr['ema21'] * 1.0015 and curr['close'] > curr['ema21']:
        buy_p["structure_m15"] = 25
        buy_reasons.append("Pullback alcista en zona EMA 21 M15")
    elif curr['close'] < curr['ema50'] and curr['high'] >= curr['ema21'] * 0.9985 and curr['close'] < curr['ema21']:
        sell_p["structure_m15"] = 25
        sell_reasons.append("Pullback bajista en zona EMA 21 M15")

    # 3. Liquidity sweep (15; el FVG suma 10 más en el copilot)
    p10l, p10h = curr['prev_10_low'], curr['prev_10_high']
    if not pd.isna(p10l) and curr['low'] < p10l and curr['close'] > p10l:
        buy_p["smc_liquidity"] = 15
        buy_reasons.append("Barrido de liquidez de mínimos")
    elif not pd.isna(p10h) and curr['high'] > p10h and curr['close'] < p10h:
        sell_p["smc_liquidity"] = 15
        sell_reasons.append("Barrido de liquidez de máximos")

    # 4. Momentum RSI / MACD (20)
    rsi_val = _num(curr, 'rsi', 50.0)
    if 40 <= rsi_val <= 65 and curr['macd_hist'] > prev['macd_hist']:
        buy_p["momentum"] = 20
        buy_reasons.append(f"Impulso alcista MACD/RSI ({rsi_val:.1f})")
    elif 35 <= rsi_val <= 60 and curr['macd_hist'] < prev['macd_hist']:
        sell_p["momentum"] = 20
        sell_reasons.append(f"Impulso bajista MACD/RSI ({rsi_val:.1f})")

    # 5. Trend strength ADX + Relative Volume (15), solo a favor del lado que domina (+DI / -DI)
    adx_val = _num(curr, 'adx', 20.0)
    rel_vol_val = _num(curr, 'rel_vol', 1.0)
    plus_di = _num(curr, 'plus_di', 0.0)
    minus_di = _num(curr, 'minus_di', 0.0)
    if adx_val >= 22 and rel_vol_val >= 1.15:
        msg = f"Fuerza direccional (ADX {adx_val:.1f}) + Volumen {rel_vol_val:.1f}x"
        if plus_di > minus_di:
            buy_p["execution_cost"] = 15
            buy_reasons.append(msg)
        elif minus_di > plus_di:
            sell_p["execution_cost"] = 15
            sell_reasons.append(msg)

    buy_score, sell_score = sum(buy_p.values()), sum(sell_p.values())

    # Spread penalty
    if spread_price > (atr * 0.20):
        buy_score = max(0, buy_score - 25)
        sell_score = max(0, sell_score - 25)
        buy_p["execution_cost"] = sell_p["execution_cost"] = 0
        note = f"⚠️ Spread alto ({spread_price:.{digits}f}) penaliza -25"
        buy_reasons.append(note)
        sell_reasons.append(note)

    if buy_score > sell_score and buy_score >= MIN_SIGNAL_SCORE:
        direction, score, reasons, pillars = "BUY", min(100, buy_score), buy_reasons, buy_p
    elif sell_score > buy_score and sell_score >= MIN_SIGNAL_SCORE:
        direction, score, reasons, pillars = "SELL", min(100, sell_score), sell_reasons, sell_p
    else:
        direction, score = "NEUTRAL", max(buy_score, sell_score)
        reasons = ["Esperando confluencia cuantitativa M15/H1"]
        pillars = buy_p if buy_score >= sell_score else sell_p
    return {"direction": direction, "score": score, "reasons": reasons, "pillars": pillars}


@dataclass
class TradingSignal:
    symbol: str
    direction: str
    score: int
    quality: str
    entry_price: float
    sl: float
    tp: float
    recommended_lot: float
    rr_ratio: float
    atr: float
    spread_points: int
    reasons: list[str]
    pillars: dict
    lot_exceeds_risk: bool

def _bar_close_ts(bar_time, seconds: int) -> float:
    """Hora de cierre (epoch, hora del servidor) de una vela a partir de su hora de apertura."""
    if isinstance(bar_time, pd.Timestamp):
        return bar_time.timestamp() + seconds
    return float(bar_time) + seconds


class QuantSignalEngine:
    def __init__(self, risk_percent: float = 1.0, atr_sl_mult: float = 1.5, atr_tp_mult: float = 3.0):
        self.risk_percent = risk_percent
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult
        self.tracker = SetupTracker()

    def _fetch_df(self, symbol: str, timeframe: int, bars: int = 250) -> Optional[pd.DataFrame]:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
        if rates is None or len(rates) < 50:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        close, high, low, vol = df['close'], df['high'], df['low'], df['tick_volume']
        df['ema21'] = close.ewm(span=21, adjust=False).mean()
        df['ema50'] = close.ewm(span=50, adjust=False).mean()
        df['ema200'] = close.ewm(span=200, adjust=False).mean()

        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        df['atr'] = tr.ewm(alpha=1/14, adjust=False).mean()

        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, np.nan))))

        ema12, ema26 = close.ewm(span=12, adjust=False).mean(), close.ewm(span=26, adjust=False).mean()
        df['macd_hist'] = (ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()

        up_move, down_move = high.diff(), -low.diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        atr_series = df['atr'].replace(0, np.nan)
        plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean() / atr_series
        minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean() / atr_series
        di_diff = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
        df['adx'] = di_diff.ewm(alpha=1/14, adjust=False).mean().fillna(20.0)
        df['plus_di'] = plus_di
        df['minus_di'] = minus_di

        df['vol_sma20'] = vol.rolling(20, min_periods=1).mean().replace(0, 1.0)
        df['rel_vol'] = (vol / df['vol_sma20']).fillna(1.0)
        df['prev_10_low'] = low.shift(2).rolling(10, min_periods=3).min()
        df['prev_10_high'] = high.shift(2).rolling(10, min_periods=3).max()
        return df

    def calculate_lot_size(self, symbol: str, sl_distance_price: float, simulated_equity: float = 100000.0, price: float = 0.0) -> tuple[float, bool]:
        """Lote que arriesga como máximo risk_percent del equity. Devuelve (lote, el_lote_minimo_supera_el_riesgo)."""
        account, sym_info = None, None
        try:
            account = mt5.account_info()
            sym_info = mt5.symbol_info(_resolved_symbols.get(symbol, symbol))
        except Exception:
            pass

        equity = account.equity if account else simulated_equity
        tick_size = sym_info.trade_tick_size if (sym_info and sym_info.trade_tick_size and sym_info.trade_tick_size > 0) else 0.01
        tick_value = sym_info.trade_tick_value if (sym_info and sym_info.trade_tick_value and sym_info.trade_tick_value > 0) else 1.0
        step = sym_info.volume_step if (sym_info and sym_info.volume_step and sym_info.volume_step > 0) else 0.01
        min_vol = sym_info.volume_min if (sym_info and sym_info.volume_min and sym_info.volume_min > 0) else 0.01
        max_vol = sym_info.volume_max if (sym_info and sym_info.volume_max and sym_info.volume_max > 0) else 100.0

        # Valores de respaldo solo si el broker no entrega la especificación del símbolo
        if not sym_info:
            if symbol == "XAUUSD":
                tick_size, tick_value = 0.01, 1.0
            elif symbol in ("EURUSD", "GBPUSD"):
                tick_size, tick_value = 0.00001, 1.0
            elif symbol == "USDJPY":
                tick_size, tick_value = 0.001, 0.65

        risk_money = equity * (self.risk_percent / 100.0)
        ticks_at_risk = sl_distance_price / tick_size if tick_size > 0 else 0
        if ticks_at_risk <= 0 or tick_value <= 0:
            return min_vol, True

        raw_lot = risk_money / (ticks_at_risk * tick_value)
        # Pérdida real de 1 lote calculada por MT5: algunos brokers reportan trade_tick_value
        # inconsistente (MetaQuotes-Demo da 0.1 en XAUUSD con contrato de 100 → lote 10x mayor)
        if sym_info and price > sl_distance_price > 0:
            try:
                loss_one_lot = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, sym_info.name, 1.0, price, price - sl_distance_price)
                if loss_one_lot is not None and abs(loss_one_lot) > 0:
                    raw_lot = risk_money / abs(loss_one_lot)
            except Exception:
                pass
        # Redondeo hacia abajo: redondear al paso más cercano podía superar el riesgo máximo
        stepped_lot = np.floor(raw_lot / step + 1e-9) * step
        if stepped_lot < min_vol:
            return round(min_vol, 2), True
        return round(min(max_vol, stepped_lot), 2), False

    def evaluate_dataframes(
        self,
        symbol: str,
        df_m15: pd.DataFrame,
        df_h1: pd.DataFrame,
        tick_bid: float,
        tick_ask: float,
        digits: int = 2,
        point: float = 0.01,
        simulated_equity: float = 100000.0,
        df_m5: Optional[pd.DataFrame] = None,
        prev_day: Optional[tuple[float, float]] = None,
        prev_week: Optional[tuple[float, float]] = None,
        now: Optional[float] = None,
    ) -> Optional[dict]:
        """Con df_m5 se construye el plan de entrada (zona, gatillo, SL/TP por estructura) y su estado;
        sin él se devuelve la señal clásica a mercado con SL/TP por ATR."""
        df_m15 = self._compute_indicators(df_m15.copy())
        df_h1 = self._compute_indicators(df_h1.copy())
        # Se evalúa la última vela CERRADA (iloc[-2]); la vela en curso aún puede cambiar
        curr, prev = df_m15.iloc[-2], df_m15.iloc[-3]
        h1_curr = df_h1.iloc[-2]

        atr = float(curr['atr']) if not pd.isna(curr['atr']) and curr['atr'] > 0 else point * 100
        spread_price = max(0.0, tick_ask - tick_bid)
        sc = score_bar(curr, prev, h1_curr, spread_price, atr, digits)
        direction, score, reasons, pillars = sc["direction"], sc["score"], sc["reasons"], sc["pillars"]
        spread_pts = int(round(spread_price / (point if point > 0 else 0.00001)))

        sl_dist = atr * self.atr_sl_mult
        if direction == "BUY":
            entry = tick_ask
            sl = round(entry - sl_dist, digits)
            tp = round(entry + (atr * self.atr_tp_mult), digits)
        elif direction == "SELL":
            entry = tick_bid
            sl = round(entry + sl_dist, digits)
            tp = round(entry - (atr * self.atr_tp_mult), digits)
        else:
            entry, sl, tp = tick_bid, 0.0, 0.0
        rr_ratio = round(self.atr_tp_mult / self.atr_sl_mult, 2)
        plan_info: dict = {}

        if df_m5 is not None:
            now = time.time() if now is None else now
            plan_dir = direction
            carried = False
            if direction == "NEUTRAL" and self.tracker.live_direction(symbol):
                plan_dir, carried = self.tracker.live_direction(symbol), True

            if plan_dir == "NEUTRAL":
                self.tracker.clear(symbol)
                plan_info = {"state": SIN_SETUP, "executable": False}
            else:
                closed15 = df_m15.iloc[:-1]
                closed_h1 = df_h1.iloc[:-1]
                closed5 = df_m5.iloc[:-1]
                price_now = tick_ask if plan_dir == "BUY" else tick_bid
                fvg = recent_fvg(closed15['open'].values, closed15['high'].values, closed15['low'].values,
                                 closed15['close'].values, plan_dir)
                levels = collect_levels(closed15['high'].values, closed15['low'].values,
                                        closed_h1['high'].values, closed_h1['low'].values, prev_day, prev_week)
                plan = build_plan(plan_dir, float(curr['ema21']), atr, closed15['low'].values[-6:],
                                  closed15['high'].values[-6:], fvg, levels, price_now, digits)
                trigger = m5_trigger(closed5['open'].values, closed5['high'].values, closed5['low'].values,
                                     closed5['close'].values, plan)
                trig_close = _bar_close_ts(closed5['time'].iloc[-1], 300)
                signal_close = None if carried else _bar_close_ts(curr['time'], 900)
                st = self.tracker.update(symbol, plan, price_now, now, signal_close, score,
                                         trigger, trig_close)
                if carried:
                    direction, score = plan_dir, st["origin_score"]
                    reasons = [f"Setup {plan_dir} de una vela M15 anterior sigue vigente"] + reasons[1:]

                # En vivo, una vez en zona/activada la entrada es a mercado; antes se planifica en el borde de la zona
                market = st["state"] in (EN_ZONA, ACTIVADA)
                entry = price_now if market else plan.entry
                sl, tp = plan.sl, plan.tp2
                rr_ratio = plan.rr_tp2
                sl_dist = abs(entry - sl)
                if st["trigger"]:
                    reasons = [f"🎯 Gatillo: {st['trigger']}"] + reasons
                if st["state_reason"]:
                    reasons = [f"⛔ {st['state_reason']}"] + reasons
                near = sorted(levels, key=lambda lv: abs(lv["price"] - price_now))[:8]
                plan_info = {
                    **st,
                    "executable": st["state"] == ACTIVADA,
                    "entry_type": "MERCADO" if market else "ZONA",
                    "zone_low": plan.zone_low,
                    "zone_high": plan.zone_high,
                    "tp1": plan.tp1,
                    "tp1_label": plan.tp1_label,
                    "tp2_label": plan.tp2_label,
                    "rr_tp1": plan.rr_tp1,
                    "rr_tp2": plan.rr_tp2,
                    "levels": [{"name": lv["name"], "price": round(lv["price"], digits)} for lv in near],
                }

        # El SL se activa con el precio contrario: la pérdida real incluye el spread
        lot, lot_exceeds_risk = self.calculate_lot_size(symbol, sl_dist + spread_price, simulated_equity, price=tick_ask)
        if direction != "NEUTRAL" and lot_exceeds_risk:
            reasons.append(f"⚠️ El lote mínimo arriesga más del {self.risk_percent}% de la cuenta")

        res = asdict(TradingSignal(
            symbol=symbol,
            direction=direction,
            score=score,
            quality="STRONG" if score >= 75 else ("MODERATE" if score >= 60 else "WAIT"),
            entry_price=round(entry, digits),
            sl=sl,
            tp=tp,
            recommended_lot=lot,
            rr_ratio=rr_ratio,
            atr=round(atr, digits),
            spread_points=spread_pts,
            reasons=reasons,
            pillars=pillars,
            lot_exceeds_risk=lot_exceeds_risk,
        ))
        res.update(plan_info)
        return res

    def evaluate_symbol(self, symbol: str) -> Optional[dict]:
        try:
            broker_symbol = resolve_symbol(symbol)
            if not broker_symbol:
                return None
            sym_info = mt5.symbol_info(broker_symbol)
            if not sym_info:
                return None

            bars = 250 + EMA_WARMUP_BARS
            df_m15 = self._fetch_df(broker_symbol, mt5.TIMEFRAME_M15, bars)
            df_h1 = self._fetch_df(broker_symbol, mt5.TIMEFRAME_H1, bars)
            df_m5 = self._fetch_df(broker_symbol, mt5.TIMEFRAME_M5, 60)
            if df_m15 is None or df_h1 is None or df_m5 is None:
                return None
            d1 = mt5.copy_rates_from_pos(broker_symbol, mt5.TIMEFRAME_D1, 1, 1)
            w1 = mt5.copy_rates_from_pos(broker_symbol, mt5.TIMEFRAME_W1, 1, 1)
            prev_day = (float(d1[0]['high']), float(d1[0]['low'])) if d1 is not None and len(d1) else None
            prev_week = (float(w1[0]['high']), float(w1[0]['low'])) if w1 is not None and len(w1) else None

            tick = mt5.symbol_info_tick(broker_symbol)
            if not tick or tick.bid <= 0:
                return None

            res = self.evaluate_dataframes(
                symbol=symbol,
                df_m15=df_m15,
                df_h1=df_h1,
                tick_bid=tick.bid,
                tick_ask=tick.ask,
                digits=sym_info.digits,
                point=sym_info.point,
                df_m5=df_m5,
                prev_day=prev_day,
                prev_week=prev_week,
            )
            res["broker_symbol"] = broker_symbol
            res["data_source"] = "MT5"
            return res
        except Exception as e:
            print(f"[Signal Error] {symbol}: {e}")
            return None
