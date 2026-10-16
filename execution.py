import math
import time
from typing import Optional

import MetaTrader5 as mt5

# Códigos de retorno de MT5 traducidos para mostrarlos en la UI
RETCODE_MESSAGES = {
    10004: "Recotización: el precio cambió, reintenta",
    10006: "Orden rechazada por el broker",
    10013: "Solicitud inválida",
    10014: "Volumen inválido para este símbolo",
    10015: "Precio inválido",
    10016: "SL/TP inválidos o demasiado cerca del precio",
    10017: "Trading deshabilitado para esta cuenta",
    10018: "Mercado cerrado",
    10019: "Fondos insuficientes",
    10020: "Los precios cambiaron, reintenta",
    10021: "Sin cotizaciones para procesar la orden",
    10024: "Demasiadas solicitudes seguidas",
    10026: "El servidor tiene deshabilitado el auto-trading",
    10027: "Algo Trading está desactivado en la terminal MT5 (activa el botón 'Algo Trading')",
    10030: "Modo de llenado no soportado por el broker",
    10031: "Sin conexión con el servidor del broker",
    10040: "Límite de posiciones abiertas alcanzado",
}

OK_RETCODES = {10008, 10009, 10010}  # PLACED, DONE, DONE_PARTIAL
# Recotización, precio cambiado, sin cotización: se reintenta con un tick nuevo (nada más se reintenta)
RETRY_RETCODES = {10004, 10020, 10021}
MAX_PRICE_RETRIES = 3
RETRY_PAUSE_SECONDS = 0.2


def retcode_message(retcode: int, comment: str = "") -> str:
    base = RETCODE_MESSAGES.get(retcode, f"Código {retcode}")
    return f"{base} ({comment})" if comment else base


def normalize_volume(volume: float, vmin: float, vmax: float, step: float) -> float:
    """Ajusta el volumen al paso del broker (hacia abajo) dentro de [min, max]."""
    if step <= 0:
        step = 0.01
    stepped = math.floor(volume / step + 1e-9) * step
    stepped = max(vmin, min(vmax, stepped))
    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return round(stepped, decimals)


def validate_levels(direction: str, price: float, sl: float, tp: float, min_distance: float) -> Optional[str]:
    """Devuelve un mensaje de error si SL/TP están del lado equivocado o más cerca que el mínimo del broker."""
    if sl <= 0 or tp <= 0:
        return "La orden necesita Stop Loss y Take Profit"
    if direction == "BUY":
        if not (sl < price < tp):
            return f"Niveles inválidos para BUY: se requiere SL < precio < TP (SL {sl}, precio {price}, TP {tp})"
        if (price - sl) < min_distance or (tp - price) < min_distance:
            return f"SL/TP a menos de la distancia mínima del broker ({min_distance})"
    elif direction == "SELL":
        if not (tp < price < sl):
            return f"Niveles inválidos para SELL: se requiere TP < precio < SL (TP {tp}, precio {price}, SL {sl})"
        if (sl - price) < min_distance or (price - tp) < min_distance:
            return f"SL/TP a menos de la distancia mínima del broker ({min_distance})"
    else:
        return f"Dirección desconocida: {direction}"
    return None


def trading_preflight(broker_symbol: str) -> Optional[str]:
    """Comprueba que la terminal, la cuenta y el símbolo permiten operar."""
    term = mt5.terminal_info()
    if not term or not term.connected:
        return "MT5 no está conectado al servidor del broker"
    if not term.trade_allowed:
        return RETCODE_MESSAGES[10027]
    acc = mt5.account_info()
    if not acc:
        return "No hay sesión iniciada en MT5"
    if not acc.trade_allowed:
        return "La cuenta no permite operar (¿contraseña de inversor?)"
    info = mt5.symbol_info(broker_symbol)
    if not info:
        return f"Símbolo {broker_symbol} no disponible en el broker"
    if info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        return f"{broker_symbol}: trading deshabilitado por el broker"
    return None


def _filling_modes(info) -> list[int]:
    modes = []
    if info.filling_mode & 2:
        modes.append(mt5.ORDER_FILLING_IOC)
    if info.filling_mode & 1:
        modes.append(mt5.ORDER_FILLING_FOK)
    modes.append(mt5.ORDER_FILLING_RETURN)
    return modes


def send_market_order(
    broker_symbol: str,
    direction: str,
    volume: float,
    sl: float,
    tp: float,
    magic: int,
    comment: str,
    deviation: int = 25,
):
    """Envía una orden a mercado validada. Devuelve (resultado_mt5 | None, mensaje_error | None, volumen_enviado)."""
    direction = direction.upper()
    err = trading_preflight(broker_symbol)
    if err:
        return None, err, 0.0

    info = mt5.symbol_info(broker_symbol)
    is_buy = direction == "BUY"
    digits = info.digits
    sl, tp = round(sl, digits), round(tp, digits)
    min_distance = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    vol = normalize_volume(volume, info.volume_min, info.volume_max, info.volume_step)

    last_error = "Sin respuesta del broker"
    for attempt in range(MAX_PRICE_RETRIES):
        if attempt:
            time.sleep(RETRY_PAUSE_SECONDS)
        result, last_error, retry = _send_once(broker_symbol, direction, is_buy, vol, sl, tp, magic, comment,
                                               deviation, info, min_distance)
        if result is not None or not retry:
            return result, last_error, vol
    return None, last_error, vol


def _send_once(broker_symbol, direction, is_buy, vol, sl, tp, magic, comment, deviation, info, min_distance):
    """Un intento con el tick actual. Devuelve (resultado | None, error | None, reintentar_con_tick_nuevo)."""
    tick = mt5.symbol_info_tick(broker_symbol)
    if not tick or tick.bid <= 0:
        return None, retcode_message(10021), True
    price = tick.ask if is_buy else tick.bid
    err = validate_levels(direction, price, sl, tp, min_distance)
    if err:
        return None, err, False

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": broker_symbol,
        "volume": vol,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": deviation,
        "magic": magic,
        "comment": comment[:31],
        "type_time": mt5.ORDER_TIME_GTC,
    }

    last_error = "Sin respuesta del broker"
    for filling in _filling_modes(info):
        request["type_filling"] = filling
        check = mt5.order_check(request)
        if check is None:
            last_error = f"order_check falló: {mt5.last_error()}"
            continue
        # order_check devuelve 0 cuando la solicitud es válida
        if check.retcode not in (0, *OK_RETCODES):
            last_error = retcode_message(check.retcode, check.comment)
            if check.retcode == 10030:
                continue
            return None, last_error, check.retcode in RETRY_RETCODES
        result = mt5.order_send(request)
        if result is None:
            last_error = f"order_send falló: {mt5.last_error()}"
            continue
        if result.retcode in OK_RETCODES:
            return result, None, False
        last_error = retcode_message(result.retcode, result.comment)
        if result.retcode != 10030:
            return None, last_error, result.retcode in RETRY_RETCODES
    return None, last_error, False


def requested_price(result) -> float | None:
    """Precio pedido en la orden (el resultado de MT5 trae la solicitud); para medir el deslizamiento."""
    req = getattr(result, "request", None)
    return float(req.price) if req is not None and getattr(req, "price", 0) else None


def split_volume(volume: float, vmin: float, step: float) -> Optional[float]:
    """Mitad del volumen ajustada al paso del broker, o None si la mitad no llega al lote mínimo."""
    if step <= 0:
        step = 0.01
    half = math.floor(volume / 2 / step + 1e-9) * step
    if half < vmin - 1e-12:
        return None
    decimals = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return round(half, decimals)


def send_plan_orders(broker_symbol: str, direction: str, volume: float, sl: float, tp1: Optional[float],
                     tp2: float, magic: int, comment: str):
    """Plan con parcial en TP1: dos órdenes de medio volumen (una con TP1 y otra con TP2) para que el BROKER cierre
    la mitad en TP1 aunque la app esté cerrada, igual que supone el backtest. Si no hay TP1 o la mitad no llega
    al lote mínimo, una sola orden a TP2 (la app hace el parcial mientras esté abierta).

    Devuelve (patas, error): patas = [(resultado, volumen, "TP1" | "TP2" | "UNICA")]. Si la segunda pata falla,
    queda abierta solo la primera (la mitad del riesgo) y se informa.
    """
    info = mt5.symbol_info(broker_symbol)
    half = split_volume(volume, info.volume_min, info.volume_step) if (info and tp1) else None
    if half is None:
        result, err, vol = send_market_order(broker_symbol, direction, volume, sl, tp2, magic, comment)
        return ([(result, vol, "UNICA")] if result else []), err
    first, err, vol1 = send_market_order(broker_symbol, direction, half, sl, tp1, magic, f"{comment} TP1")
    if not first:
        return [], err
    second, err, vol2 = send_market_order(broker_symbol, direction, half, sl, tp2, magic, f"{comment} TP2")
    if not second:
        return [(first, vol1, "TP1")], f"Solo se abrió la mitad con TP1: {err}"
    return [(first, vol1, "TP1"), (second, vol2, "TP2")], None
