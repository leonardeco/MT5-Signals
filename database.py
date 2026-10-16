from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
import MetaTrader5 as mt5

from journal import finalize_closed_trade

DATABASE_URL = "sqlite:///./quant_terminal.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TradeRecord(Base):
    __tablename__ = "trade_records"

    id = Column(Integer, primary_key=True, index=True)
    ticket = Column(Integer, unique=True, index=True)
    symbol = Column(String(20), index=True)
    direction = Column(String(10))
    volume_initial = Column(Float)
    entry_price = Column(Float)
    sl_initial = Column(Float)
    tp_initial = Column(Float)
    tp1 = Column(Float, nullable=True)  # objetivo parcial (50%) del plan; tp_initial es el TP2
    signal_score = Column(Integer)
    status = Column(String(20), default="OPEN")  # OPEN, CLOSED
    profit = Column(Float, default=0.0)
    close_price = Column(Float, nullable=True)
    open_time = Column(DateTime, default=datetime.utcnow)
    close_time = Column(DateTime, nullable=True)
    # Órdenes divididas: las dos patas comparten group_id (ticket de la pata TP1); leg = TP1 | TP2 | UNICA
    group_id = Column(Integer, nullable=True, index=True)
    leg = Column(String(10), nullable=True)
    requested_price = Column(Float, nullable=True)  # precio pedido: entry_price − requested_price = deslizamiento
    r_multiple = Column(Float, nullable=True)       # resultado en R (beneficio / dinero en riesgo al SL inicial)
    mae_r = Column(Float, nullable=True)            # peor excursión en contra durante la operación, en R
    mfe_r = Column(Float, nullable=True)            # mejor excursión a favor, en R

class KillSwitchEvent(Base):
    __tablename__ = "kill_switch_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    starting_balance = Column(Float)
    trigger_equity = Column(Float)
    daily_loss_pct = Column(Float)
    reason = Column(Text)

class SignalLog(Base):
    __tablename__ = "signal_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    symbol = Column(String(20), index=True)
    direction = Column(String(10))
    score = Column(Integer)
    quality = Column(String(20))
    entry_price = Column(Float)
    sl = Column(Float)
    tp = Column(Float)
    reasons = Column(Text)

class DailyRiskState(Base):
    """Balance de inicio del día y estado del kill switch; sobrevive a reinicios de la app."""
    __tablename__ = "daily_risk_state"

    day = Column(String(10), primary_key=True)  # YYYY-MM-DD (hora local)
    starting_balance = Column(Float)
    locked = Column(Integer, default=0)
    lock_reason = Column(Text, default="")

TRADE_RECORD_ADDED_COLUMNS = {
    "tp1": "FLOAT", "group_id": "INTEGER", "leg": "VARCHAR(10)", "requested_price": "FLOAT",
    "r_multiple": "FLOAT", "mae_r": "FLOAT", "mfe_r": "FLOAT",
}

def init_db():
    Base.metadata.create_all(bind=engine)
    # create_all no añade columnas a tablas existentes: migración mínima para bases creadas antes
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(trade_records)")}
        for name, sql_type in TRADE_RECORD_ADDED_COLUMNS.items():
            if name not in cols:
                conn.exec_driver_sql(f"ALTER TABLE trade_records ADD COLUMN {name} {sql_type}")

def log_strong_signal_if_new(db, res: dict):
    # Se registra cada activación (gatillo confirmado), no cada escaneo
    if not res or res.get("direction") == "NEUTRAL" or res.get("state") != "ACTIVADA":
        return
    
    symbol = res.get("symbol")
    direction = res.get("direction")
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    
    recent = db.query(SignalLog).filter(
        SignalLog.symbol == symbol,
        SignalLog.direction == direction,
        SignalLog.timestamp >= cutoff
    ).first()

    if not recent:
        new_log = SignalLog(
            symbol=symbol,
            direction=direction,
            score=res.get("score", 0),
            quality=res.get("quality", "MODERATE"),
            entry_price=res.get("entry_price", 0.0),
            sl=res.get("sl", 0.0),
            tp=res.get("tp", 0.0),
            reasons=" | ".join(res.get("reasons", []))
        )
        db.add(new_log)
        db.commit()

def sync_open_trades_with_mt5_history(db):
    open_trades = db.query(TradeRecord).filter(TradeRecord.status == "OPEN").all()
    if not open_trades:
        return

    # Check if position is still open in active positions
    try:
        current_positions = {p.ticket: p for p in (mt5.positions_get() or [])}
    except Exception:
        return

    from_date = datetime.now() - timedelta(days=7)
    for trade in open_trades:
        if trade.ticket not in current_positions:
            # Position is no longer in active positions, check history deals
            try:
                deals = mt5.history_deals_get(position=trade.ticket)
                if deals and len(deals) > 1:
                    close_deal = deals[-1]
                    total_profit = sum(d.profit + d.swap + d.commission for d in deals)
                    trade.status = "CLOSED"
                    trade.profit = round(total_profit, 2)
                    trade.close_price = close_deal.price
                    trade.close_time = datetime.fromtimestamp(close_deal.time)
                    finalize_closed_trade(trade, deals, mt5)
                else:
                    # Still mark as closed if not in active positions
                    trade.status = "CLOSED"
                    trade.close_time = datetime.utcnow()
                db.commit()
            except Exception:
                pass
