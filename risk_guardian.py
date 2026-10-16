from datetime import datetime, date
import MetaTrader5 as mt5

from database import SessionLocal, DailyRiskState

class DailyKillSwitch:
    def __init__(self, max_daily_loss_pct: float = 3.0, magic: int | None = None):
        self.max_daily_loss_pct = max_daily_loss_pct
        self.magic = magic  # solo se liquidan las posiciones con este magic (las del bot)
        self.starting_balance = None
        self.current_date = date.today()
        self.state = {
            "locked": False,
            "lock_reason": ""
        }

    def _load_today(self):
        """Recupera el balance inicial y el bloqueo de hoy si la app se reinició."""
        try:
            with SessionLocal() as db:
                row = db.get(DailyRiskState, self.current_date.isoformat())
                if row:
                    self.starting_balance = row.starting_balance
                    self.state["locked"] = bool(row.locked)
                    self.state["lock_reason"] = row.lock_reason or ""
        except Exception as e:
            print(f"[Risk] No se pudo leer el estado diario: {e}")

    def _save_today(self):
        try:
            with SessionLocal() as db:
                row = db.get(DailyRiskState, self.current_date.isoformat())
                if not row:
                    row = DailyRiskState(day=self.current_date.isoformat())
                    db.add(row)
                row.starting_balance = self.starting_balance
                row.locked = int(bool(self.state["locked"]))
                row.lock_reason = self.state["lock_reason"]
                db.commit()
        except Exception as e:
            print(f"[Risk] No se pudo guardar el estado diario: {e}")

    def emergency_close_all(self):
        """Cierra a mercado las posiciones del bot. Las manuales o de otros EAs (otro magic) no se tocan."""
        positions = [p for p in (mt5.positions_get() or []) if self.magic is None or p.magic == self.magic]
        closed_count = 0
        for pos in positions:
            sym_info = mt5.symbol_info(pos.symbol)
            tick = mt5.symbol_info_tick(pos.symbol)
            if not sym_info or not tick:
                continue
            
            is_buy = (pos.type == mt5.POSITION_TYPE_BUY)
            filling = mt5.ORDER_FILLING_IOC if (sym_info.filling_mode & 2) else mt5.ORDER_FILLING_FOK
            order_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                "price": tick.bid if is_buy else tick.ask,
                "deviation": 30,
                "magic": pos.magic,
                "comment": "KillSwitch Emergency Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling
            }
            res = mt5.order_send(order_req)
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
        return closed_count

    def check_account_safety(self) -> dict:
        today = date.today()
        if today != self.current_date:
            self.current_date = today
            self.starting_balance = None
            self.state["locked"] = False
            self.state["lock_reason"] = ""

        acc = mt5.account_info()
        if not acc:
            return {
                "locked": self.state["locked"],
                "starting_balance": self.starting_balance or 0.0,
                "current_equity": 0.0,
                "current_balance": 0.0,
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
                "lock_reason": self.state["lock_reason"],
                "max_daily_loss_pct": self.max_daily_loss_pct
            }

        if self.starting_balance is None or self.starting_balance <= 0:
            self._load_today()
        if self.starting_balance is None or self.starting_balance <= 0:
            self.starting_balance = float(acc.balance)
            self._save_today()

        daily_pnl = float(acc.equity - self.starting_balance)
        daily_pnl_pct = (daily_pnl / self.starting_balance) * 100.0 if self.starting_balance > 0 else 0.0

        if not self.state["locked"] and daily_pnl_pct <= -abs(self.max_daily_loss_pct):
            self.state["locked"] = True
            self.state["lock_reason"] = (
                f"🚨 KILL SWITCH ACTIVADO: Pérdida diaria {daily_pnl_pct:.2f}% "
                f"superó el límite de seguridad ({self.max_daily_loss_pct}%). "
                f"Trading bloqueado y posiciones del bot liquidadas (las manuales siguen abiertas)."
            )
            self._save_today()
            self.emergency_close_all()

        return {
            "locked": self.state["locked"],
            "starting_balance": round(self.starting_balance, 2),
            "current_equity": round(acc.equity, 2),
            "current_balance": round(acc.balance, 2),
            "daily_pnl": round(daily_pnl, 2),
            "daily_pnl_pct": round(daily_pnl_pct, 2),
            "lock_reason": self.state["lock_reason"],
            "max_daily_loss_pct": self.max_daily_loss_pct
        }

    def reset_lock(self):
        acc = mt5.account_info()
        if acc:
            self.starting_balance = float(acc.balance)
        self.state["locked"] = False
        self.state["lock_reason"] = ""
        self._save_today()
        return {"status": "unlocked", "starting_balance": self.starting_balance}
