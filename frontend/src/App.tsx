import React, { useEffect, useState, useRef } from 'react';
import type { MarketUpdate, TradingSignal } from './types';
import { Header } from './components/Header';
import { LightweightChart } from './components/LightweightChart';
import { SignalsPanel } from './components/SignalsPanel';
import { BotCopilotPanel } from './components/BotCopilotPanel';
import { PositionsPanel } from './components/PositionsPanel';
import { JournalPanel } from './components/JournalPanel';
import { BacktestPanel } from './components/BacktestPanel';
import { ForwardPanel } from './components/ForwardPanel';
import { AlertTriangle, Info } from 'lucide-react';
import { apiFetch, getApiBase, wsUrl } from './api';

const WATCHLIST = ['XAUUSD', 'EURUSD', 'GBPUSD', 'US100', 'USDJPY'];

export const App: React.FC = () => {
  const [marketData, setMarketData] = useState<MarketUpdate>({
    type: 'MARKET_UPDATE',
    account: { balance: 0, equity: 0, profit: 0 },
    risk: {
      locked: false,
      starting_balance: 0,
      current_equity: 0,
      current_balance: 0,
      daily_pnl: 0,
      daily_pnl_pct: 0,
      lock_reason: '',
      max_daily_loss_pct: 3.0,
    },
    autotrading: false,
    bot_logs: [],
    bot_mode: 'INSTITUTIONAL',
    signals: [],
    positions: [],
  });

  const [selectedSymbol, setSelectedSymbol] = useState<string>('XAUUSD');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const toastTimeoutRef = useRef<any>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 6000);
  };

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let closed = false;
    let wsAlive = false;

    const apply = (payload: { type?: string }) => {
      if (payload.type === 'MARKET_UPDATE') setMarketData(payload as MarketUpdate);
    };

    const poll = async () => {
      if (wsAlive) return;
      try {
        const res = await apiFetch('/market');
        if (!res.ok) throw new Error('sin respuesta');
        apply(await res.json());
        setWsConnected(true);
      } catch {
        setWsConnected(false);
      }
    };

    const connect = () => {
      ws = new WebSocket(wsUrl('/ws/signals'));
      ws.onopen = () => {
        wsAlive = true;
        setWsConnected(true);
      };
      ws.onmessage = (event) => {
        try {
          apply(JSON.parse(event.data));
        } catch (e) {
          console.error('Error parsing market update:', e);
        }
      };
      ws.onclose = () => {
        wsAlive = false;
        if (closed) return;
        setWsConnected(false);
        reconnectTimer = window.setTimeout(connect, 2000);
      };
      ws.onerror = () => {
        wsAlive = false;
        ws?.close();
      };
    };

    connect();
    const pollTimer = window.setInterval(poll, 2000);

    return () => {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      window.clearInterval(pollTimer);
      ws?.close();
    };
  }, []);

  const handleResetRisk = async () => {
    if (!window.confirm('El bloqueo corta el día a propósito. ¿Desbloquear el kill switch y volver a permitir órdenes?')) return;
    try {
      const res = await apiFetch('/risk/reset', { method: 'POST' });
      if (res.ok) {
        showToast('🛡️ Kill Switch reiniciado con éxito');
      }
    } catch (err: any) {
      showToast(`Error al reiniciar: ${err.message}`);
    }
  };

  const handleToggleAutoTrading = async (enabled: boolean) => {
    try {
      const res = await apiFetch('/bot/autotrading', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Fallo');
      showToast(enabled ? '🤖 Auto-Trading Activado' : '⏸️ Auto-Trading Pausado');
    } catch (err: any) {
      showToast(`Aviso: ${err.message}`);
    }
  };

  const handleChangeBotMode = async (mode: 'SNIPER' | 'INSTITUTIONAL' | 'DYNAMIC') => {
    try {
      const res = await apiFetch('/bot/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (res.ok) {
        showToast(`⚙️ Modo del Copilot cambiado a ${mode}`);
      }
    } catch (err: any) {
      showToast(`Error: ${err.message}`);
    }
  };

  const activeSignal: TradingSignal | undefined = marketData.signals.find(
    (s) => s.symbol === selectedSymbol
  );

  return (
    <div className="terminal-shell">
      
      {/* Top Header */}
      <Header
        account={marketData.account}
        risk={marketData.risk}
        autotrading={marketData.autotrading}
        wsConnected={wsConnected}
        mt5Connected={marketData.mt5_connected}
        onResetRisk={handleResetRisk}
        onToggleAutoTrading={handleToggleAutoTrading}
      />

      {!wsConnected && (
        <div style={{
          background: 'rgba(245, 158, 11, 0.12)',
          border: '1px solid rgba(245, 158, 11, 0.45)',
          borderRadius: '10px',
          padding: '12px 18px',
          marginBottom: '18px',
          color: '#ffffff',
          fontSize: '0.85rem',
          lineHeight: 1.45,
        }}>
          <strong style={{ color: '#fcd34d' }}>Motor sin respuesta en {getApiBase()}.</strong>{' '}
          MetaTrader 5 y el backend viven en este PC: ejecuta <span className="num-mono">start_terminal.bat</span> y opera en{' '}
          <span className="num-mono">http://localhost:5173</span>. Esta página publicada solo alcanza el motor si el navegador está en el mismo equipo.
        </div>
      )}

      {/* Sin MT5 no hay precios reales: avisar antes que cualquier señal */}
      {wsConnected && marketData.mt5_connected === false && (
        <div style={{
          background: 'rgba(239, 68, 68, 0.18)',
          border: '1px solid #ef4444',
          borderRadius: '10px',
          padding: '12px 18px',
          marginBottom: '18px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          color: '#ffffff'
        }}>
          <AlertTriangle size={22} color="#ef4444" />
          <div style={{ fontSize: '0.85rem' }}>
            <strong style={{ color: '#fca5a5' }}>MT5 DESCONECTADO — SIN PRECIOS REALES.</strong>{' '}
            Las velas son simuladas y no se generan señales ni órdenes. Abre MetaTrader 5 en este PC e inicia sesión en tu cuenta; la app se reconecta sola en unos segundos.
            {marketData.mt5_status && (
              <div style={{ marginTop: '4px', color: '#fca5a5', fontWeight: 600 }}>Motivo: {marketData.mt5_status}</div>
            )}
          </div>
        </div>
      )}

      {/* Kill Switch Critical Alert Banner */}
      {marketData.risk?.locked && (
        <div style={{
          background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.25) 0%, rgba(185, 28, 28, 0.4) 100%)',
          border: '1px solid #ef4444',
          borderRadius: '10px',
          padding: '12px 18px',
          marginBottom: '18px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          color: '#ffffff'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertTriangle size={22} color="#ef4444" />
            <div>
              <strong style={{ fontSize: '0.9rem', color: '#fca5a5' }}>
                BLOQUEO DE SEGURIDAD ACTIVO:
              </strong>{' '}
              <span style={{ fontSize: '0.85rem' }}>{marketData.risk.lock_reason}</span>
            </div>
          </div>
          <button
            onClick={handleResetRisk}
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              background: '#ef4444',
              color: '#ffffff',
              fontSize: '0.78rem',
              fontWeight: 700
            }}
          >
            Desbloquear Terminal
          </button>
        </div>
      )}

      {/* Floating Status Toast */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          zIndex: 9999,
          background: '#0f172a',
          border: '1px solid #38bdf8',
          borderRadius: '10px',
          padding: '12px 18px',
          boxShadow: '0 8px 30px rgba(0, 0, 0, 0.6)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          color: '#ffffff',
          fontSize: '0.85rem',
          fontWeight: 600
        }}>
          <Info size={16} color="#38bdf8" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Main Grid: 2 Columns */}
      <div className="terminal-grid">
        
        {/* Left Column: Chart, Open Positions, Journal */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          <LightweightChart
            symbol={selectedSymbol}
            activeSignal={activeSignal}
            onSelectSymbol={setSelectedSymbol}
            watchlist={WATCHLIST}
          />

          <PositionsPanel
            positions={marketData.positions}
            onPositionClosed={(msg) => showToast(msg)}
          />

          <BacktestPanel onMessage={(msg) => showToast(msg)} />

          <ForwardPanel onMessage={(msg) => showToast(msg)} />

          <JournalPanel />

        </div>

        {/* Right Column: Copilot Radar & Quantitative Signals */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          <BotCopilotPanel
            selectedSignal={activeSignal}
            botMode={marketData.bot_mode}
            botLogs={marketData.bot_logs}
            onChangeMode={handleChangeBotMode}
          />

          <SignalsPanel
            signals={marketData.signals}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={setSelectedSymbol}
            onOrderExecuted={(msg) => showToast(msg)}
          />

        </div>

      </div>

    </div>
  );
};

export default App;
