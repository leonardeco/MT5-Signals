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
import { AlertTriangle, Info, RefreshCw, Eye } from 'lucide-react';
import { apiFetch, checkEngine, getApiBase, LOCAL_PANEL_URL, wsUrl } from './api';
import type { EngineStatus } from './api';

const WATCHLIST = ['XAUUSD', 'EURUSD', 'GBPUSD', 'US100', 'USDJPY'];

const EMPTY_MARKET: MarketUpdate = {
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
};

export const App: React.FC = () => {
  const [marketData, setMarketData] = useState<MarketUpdate>(EMPTY_MARKET);

  const [selectedSymbol, setSelectedSymbol] = useState<string>('XAUUSD');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [engine, setEngine] = useState<EngineStatus>({ state: 'checking', canTrade: false, localPanel: LOCAL_PANEL_URL });
  const [retryKey, setRetryKey] = useState(0);
  const toastTimeoutRef = useRef<any>(null);
  const engineOk = engine.state === 'ok';
  const readOnly = engineOk && !engine.canTrade;
  const isLocalPanel = ['localhost', '127.0.0.1'].includes(window.location.hostname);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = setTimeout(() => {
      setToastMessage(null);
    }, 6000);
  };

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let wsAlive = false;

    const apply = (payload: { type?: string }) => {
      if (payload.type === 'MARKET_UPDATE') setMarketData(payload as MarketUpdate);
    };

    const openSocket = () => {
      if (closed || ws) return;
      const sock = new WebSocket(wsUrl('/ws/signals'));
      ws = sock;
      sock.onopen = () => { wsAlive = true; };
      sock.onmessage = (event) => {
        try {
          apply(JSON.parse(event.data));
        } catch (e) {
          console.error('Error parsing market update:', e);
        }
      };
      sock.onclose = () => {
        wsAlive = false;
        if (ws === sock) ws = null;
      };
      sock.onerror = () => sock.close();
    };

    // Sin WebSocket vivo: confirmar que en esa dirección responde este motor y no otra API, y leer por HTTP
    const tick = async () => {
      if (wsAlive) return;
      const status = await checkEngine();
      if (closed) return;
      setEngine(status);
      if (status.state !== 'ok') {
        setMarketData(EMPTY_MARKET);
        return;
      }
      openSocket();
      try {
        const res = await apiFetch('/market', { cache: 'no-store' });
        if (res.ok && !closed) apply(await res.json());
      } catch {
        /* el siguiente ciclo lo vuelve a intentar */
      }
    };

    tick();
    const timer = window.setInterval(tick, 3000);

    return () => {
      closed = true;
      window.clearInterval(timer);
      ws?.close();
    };
  }, [retryKey]);

  const postAction = async (path: string, body?: unknown) => {
    const res = await apiFetch(path, {
      method: 'POST',
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
    return data;
  };

  const handleResetRisk = async () => {
    if (!window.confirm('El bloqueo corta el día a propósito. ¿Desbloquear el kill switch y volver a permitir órdenes?')) return;
    try {
      await postAction('/risk/reset');
      showToast('🛡️ Kill Switch reiniciado con éxito');
    } catch (err: any) {
      showToast(`Error al reiniciar: ${err.message}`);
    }
  };

  const handleToggleAutoTrading = async (enabled: boolean) => {
    try {
      await postAction('/bot/autotrading', { enabled });
      showToast(enabled ? '🤖 Auto-Trading Activado' : '⏸️ Auto-Trading Pausado');
    } catch (err: any) {
      showToast(`Aviso: ${err.message}`);
    }
  };

  const handleChangeBotMode = async (mode: 'SNIPER' | 'INSTITUTIONAL' | 'DYNAMIC') => {
    try {
      await postAction('/bot/mode', { mode });
      showToast(`⚙️ Modo del Copilot cambiado a ${mode}`);
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
        wsConnected={engineOk}
        mt5Connected={marketData.mt5_connected}
        canTrade={!readOnly}
        onResetRisk={handleResetRisk}
        onToggleAutoTrading={handleToggleAutoTrading}
      />

      {(engine.state === 'offline' || engine.state === 'foreign') && (
        <div className="notice notice-warn">
          <AlertTriangle size={20} color="#f59e0b" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            {engine.state === 'foreign' ? (
              <>
                <strong>En {getApiBase()} responde otra aplicación, no el motor de MT5 Señales.</strong>
                <div>
                  Otro proyecto está usando ese puerto. Arranca el motor con <span className="num-mono">start_terminal.bat</span>{' '}
                  (usa el puerto 8765) o cambia la dirección con el engranaje.
                </div>
              </>
            ) : (
              <>
                <strong>No encuentro el motor en {getApiBase()}.</strong>
                <ol>
                  <li>Abre MetaTrader 5 e inicia sesión en tu cuenta.</li>
                  <li>Ejecuta <span className="num-mono">start_terminal.bat</span> en el PC donde está MetaTrader.</li>
                  {!isLocalPanel && (
                    <li>
                      Si el navegador pregunta si esta página puede acceder a dispositivos de tu red local, pulsa «Permitir».
                      Solo funciona en el mismo PC del motor.
                    </li>
                  )}
                </ol>
              </>
            )}
          </div>
          <div className="notice-actions">
            <button className="btn-ghost" onClick={() => setRetryKey((k) => k + 1)}>
              <RefreshCw size={13} /> Reintentar
            </button>
            {!isLocalPanel && (
              <a className="btn-ghost" href={engine.localPanel}>Abrir panel local</a>
            )}
          </div>
        </div>
      )}

      {readOnly && (
        <div className="notice notice-info">
          <Eye size={18} color="#38bdf8" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <strong>Panel de solo lectura.</strong> Ves precios, señales y posiciones; las órdenes, cierres y el kill switch
            se manejan desde el panel local.
          </div>
          <div className="notice-actions">
            <a className="btn-ghost" href={engine.localPanel}>Abrir panel local</a>
          </div>
        </div>
      )}

      {/* Sin MT5 no hay precios reales: avisar antes que cualquier señal */}
      {engineOk && marketData.mt5_connected === false && (
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
          {!readOnly && <button
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
          </button>}
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
            readOnly={readOnly}
          />

          {/* key: vuelven a cargar sus datos cuando el motor aparece */}
          <BacktestPanel key={`bt-${engineOk}`} onMessage={(msg) => showToast(msg)} />

          <ForwardPanel key={`fw-${engineOk}`} onMessage={(msg) => showToast(msg)} />

          <JournalPanel key={`jr-${engineOk}`} />

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
            readOnly={readOnly}
          />

        </div>

      </div>

    </div>
  );
};

export default App;
