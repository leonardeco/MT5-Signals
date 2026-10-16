import React, { useState } from 'react';
import type { AccountInfo, RiskStatus } from '../types';
import { ShieldAlert, ShieldCheck, Zap, Activity, RefreshCw, Settings } from 'lucide-react';
import { getApiBase, setApiBase } from '../api';

interface HeaderProps {
  account: AccountInfo | null;
  risk: RiskStatus | null;
  autotrading: boolean;
  wsConnected: boolean;
  mt5Connected?: boolean;
  onResetRisk: () => void;
  onToggleAutoTrading: (enabled: boolean) => void;
}

export const Header: React.FC<HeaderProps> = ({
  account,
  risk,
  autotrading,
  wsConnected,
  mt5Connected = false,
  onResetRisk,
  onToggleAutoTrading
}) => {
  const isProfitPos = (account?.profit ?? 0) >= 0;
  const isRiskLocked = risk?.locked ?? false;
  const [apiOpen, setApiOpen] = useState(false);
  const [apiDraft, setApiDraft] = useState(getApiBase);
  const money = (n?: number) => (n ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <header className="glass-panel" style={{ padding: '16px 24px', marginBottom: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        
        {/* Branding & Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            width: '44px',
            height: '44px',
            borderRadius: '10px',
            background: 'linear-gradient(135deg, #0ea5e9 0%, #6366f1 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 14px rgba(14, 165, 233, 0.4)'
          }}>
            <Zap size={24} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 800, letterSpacing: '-0.02em', margin: 0, color: '#ffffff' }}>
                MT5 QUANT PRO
              </h1>
              <span style={{
                fontSize: '0.7rem',
                fontWeight: 700,
                textTransform: 'uppercase',
                padding: '2px 8px',
                borderRadius: '6px',
                background: mt5Connected ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                color: mt5Connected ? '#10b981' : '#f59e0b',
                border: `1px solid ${mt5Connected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`
              }}>
                {mt5Connected ? 'MT5 CONECTADO' : 'SIN TERMINAL'}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              <span className={wsConnected ? 'pulse-dot' : 'pulse-dot pulse-dot-red'} style={{ backgroundColor: wsConnected ? (mt5Connected ? '#10b981' : '#f59e0b') : '#ef4444' }} />
              <span style={{ color: wsConnected ? (mt5Connected ? '#10b981' : '#f59e0b') : '#ef4444', fontWeight: 600 }}>
                {wsConnected
                  ? (mt5Connected ? 'Terminal MetaTrader recibiendo precios' : 'Sin precios reales: abre MetaTrader 5 en este PC')
                  : 'Buscando el motor...'}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>•</span>
              <span style={{ color: autotrading ? '#10b981' : 'var(--text-secondary)', fontWeight: 600 }}>
                {autotrading ? '🤖 Auto-Trading ACTIVO' : '⏸️ Modo Asistido (Manual)'}
              </span>
            </div>
          </div>
        </div>

        {/* Telemetry Numbers & Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flexWrap: 'wrap' }}>
          
          {/* Account Metrics */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            background: 'var(--bg-inset)',
            padding: '8px 16px',
            borderRadius: '10px',
            border: '1px solid var(--border-subtle)'
          }}>
            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Balance</div>
              <div className="num-mono" style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f8fafc' }}>
                ${money(account?.balance)}
              </div>
            </div>

            <div style={{ width: '1px', height: '24px', background: 'var(--border-subtle)' }} />

            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Equidad</div>
              <div className="num-mono" style={{ fontSize: '1.05rem', fontWeight: 700, color: '#38bdf8' }}>
                ${money(account?.equity)}
              </div>
            </div>

            <div style={{ width: '1px', height: '24px', background: 'var(--border-subtle)' }} />

            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Flotante PnL</div>
              <div className="num-mono" style={{
                fontSize: '1.05rem',
                fontWeight: 700,
                color: isProfitPos ? 'var(--accent-buy)' : 'var(--accent-sell)'
              }}>
                {isProfitPos ? '+' : ''}${money(account?.profit)}
              </div>
            </div>

            <div style={{ width: '1px', height: '24px', background: 'var(--border-subtle)' }} />

            <div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Margen libre</div>
              <div className="num-mono" style={{ fontSize: '1.05rem', fontWeight: 700, color: '#e2e8f0' }}>
                ${money(account?.free_margin)}
              </div>
            </div>
          </div>

          {/* Kill Switch Risk Guardian */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '8px 14px',
            borderRadius: '10px',
            background: isRiskLocked ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.08)',
            border: isRiskLocked ? '1px solid #ef4444' : '1px solid rgba(16, 185, 129, 0.2)'
          }}>
            {isRiskLocked ? <ShieldAlert size={20} color="#ef4444" /> : <ShieldCheck size={20} color="#10b981" />}
            <div>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                Kill Switch (Max -{risk?.max_daily_loss_pct ?? 3}%)
              </div>
              <div className="num-mono" style={{
                fontSize: '0.9rem',
                fontWeight: 700,
                color: (risk?.daily_pnl_pct ?? 0) < 0 ? '#ef4444' : '#10b981'
              }}>
                PnL hoy: {(risk?.daily_pnl ?? 0) >= 0 ? '+' : ''}${money(risk?.daily_pnl)} ({(risk?.daily_pnl_pct ?? 0) >= 0 ? '+' : ''}{risk?.daily_pnl_pct?.toFixed(2) ?? '0.00'}%)
              </div>
            </div>

            {isRiskLocked && (
              <button
                onClick={onResetRisk}
                title="Restablecer Kill Switch"
                style={{
                  padding: '6px 10px',
                  borderRadius: '6px',
                  border: 'none',
                  background: '#ef4444',
                  color: '#ffffff',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
              >
                <RefreshCw size={12} />
                Desbloquear
              </button>
            )}
          </div>

          {/* Auto-Trading Master Switch */}
          <button
            onClick={() => onToggleAutoTrading(!autotrading)}
            disabled={isRiskLocked}
            style={{
              padding: '10px 18px',
              borderRadius: '10px',
              border: 'none',
              background: isRiskLocked
                ? '#334155'
                : autotrading
                ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                : 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              boxShadow: autotrading ? '0 4px 14px rgba(16, 185, 129, 0.4)' : '0 4px 14px rgba(59, 130, 246, 0.3)',
              cursor: isRiskLocked ? 'not-allowed' : 'pointer'
            }}
          >
            <Activity size={16} />
            {autotrading ? 'Auto-Trading ACTIVO' : 'Activar Auto-Trading'}
          </button>

          <div style={{ position: 'relative' }}>
            <button
              onClick={() => { setApiDraft(getApiBase()); setApiOpen((v) => !v); }}
              title="Dirección del motor"
              style={{
                padding: '10px',
                borderRadius: '10px',
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-inset)',
                color: '#e2e8f0',
                display: 'flex',
              }}
            >
              <Settings size={16} />
            </button>
            {apiOpen && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setApiBase(apiDraft);
                  window.location.reload();
                }}
                style={{
                  position: 'absolute',
                  right: 0,
                  top: '46px',
                  zIndex: 20,
                  width: '320px',
                  padding: '12px',
                  borderRadius: '10px',
                  background: '#0f172a',
                  border: '1px solid var(--border-subtle)',
                  boxShadow: '0 12px 40px rgba(0,0,0,0.45)',
                }}
              >
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  Motor (en este PC es http://127.0.0.1:8000). Cámbialo solo si el backend tiene otra dirección https.
                </div>
                <input
                  value={apiDraft}
                  onChange={(e) => setApiDraft(e.target.value)}
                  spellCheck={false}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: '8px',
                    border: '1px solid var(--border-subtle)',
                    background: '#090e1a',
                    color: '#f8fafc',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.78rem',
                  }}
                />
                <button
                  type="submit"
                  style={{
                    marginTop: '8px',
                    padding: '6px 12px',
                    borderRadius: '8px',
                    border: 'none',
                    background: '#2563eb',
                    color: '#fff',
                    fontWeight: 700,
                    fontSize: '0.75rem',
                  }}
                >
                  Guardar y recargar
                </button>
              </form>
            )}
          </div>

        </div>
      </div>
    </header>
  );
};
