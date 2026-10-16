import React from 'react';
import type { TradingSignal, BotLog } from '../types';
import { Bot, Terminal, Shield, Clock, Globe } from 'lucide-react';

// Igual que min_score_map en quant_bot_copilot.py
const MODE_MIN_SCORE = { SNIPER: 85, INSTITUTIONAL: 75, DYNAMIC: 65 } as const;

interface BotCopilotProps {
  selectedSignal?: TradingSignal;
  botMode: 'SNIPER' | 'INSTITUTIONAL' | 'DYNAMIC';
  botLogs: BotLog[];
  onChangeMode: (mode: 'SNIPER' | 'INSTITUTIONAL' | 'DYNAMIC') => void;
}

export const BotCopilotPanel: React.FC<BotCopilotProps> = ({
  selectedSignal,
  botMode,
  botLogs,
  onChangeMode
}) => {
  const pillars = selectedSignal?.pillars ?? {
    macro_h1: 0,
    structure_m15: 0,
    smc_liquidity: 0,
    momentum: 0,
    execution_cost: 0
  };

  const getLogBadgeStyle = (level: string) => {
    switch (level) {
      case 'CRITICAL': return { bg: 'rgba(239, 68, 68, 0.2)', text: '#ef4444' };
      case 'PROFIT': return { bg: 'rgba(16, 185, 129, 0.2)', text: '#10b981' };
      case 'SIGNAL': return { bg: 'rgba(56, 189, 248, 0.2)', text: '#38bdf8' };
      case 'TRADE': return { bg: 'rgba(168, 85, 247, 0.2)', text: '#c084fc' };
      case 'SYSTEM': return { bg: 'rgba(245, 158, 11, 0.2)', text: '#fbbf24' };
      default: return { bg: 'rgba(100, 116, 139, 0.2)', text: '#94a3b8' };
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      
      {/* Bot Copilot Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot size={20} color="#38bdf8" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>
            QuantBot Copilot
          </h2>
        </div>

        {/* Mode Selector */}
        <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-inset)', padding: '3px', borderRadius: '8px' }}>
          {(['SNIPER', 'INSTITUTIONAL', 'DYNAMIC'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => onChangeMode(mode)}
              title={`Score mínimo ${MODE_MIN_SCORE[mode]}. Solo filtra cantidad: en el backtest un score más alto no dio mejores resultados.`}
              style={{
                padding: '4px 8px',
                borderRadius: '6px',
                border: 'none',
                background: botMode === mode ? 'linear-gradient(135deg, #0284c7 0%, #2563eb 100%)' : 'transparent',
                color: botMode === mode ? '#ffffff' : 'var(--text-muted)',
                fontSize: '0.68rem',
                fontWeight: 700,
                letterSpacing: '0.02em',
              }}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* 5 Confluence Pillars Breakdown */}
      <div style={{
        background: 'var(--bg-inset)',
        padding: '14px',
        borderRadius: '10px',
        border: '1px solid var(--border-subtle)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
          <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#f8fafc' }}>
            Desglose de Confluencia: {selectedSignal?.symbol ?? 'Seleccione activo'}
          </span>
          <span className="num-mono" style={{ fontSize: '0.85rem', fontWeight: 800, color: '#38bdf8' }}>
            {selectedSignal?.score ?? 0}/100
          </span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>
              <span>1. Macro Tendencia H1 (EMA 50/200)</span>
              <span className="num-mono">{pillars.macro_h1}/25 pts</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '2px' }}>
              <div style={{ width: `${(pillars.macro_h1 / 25) * 100}%`, height: '100%', background: '#38bdf8', borderRadius: '2px' }} />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>
              <span>2. Estructura M15 y Pullback (EMA 21)</span>
              <span className="num-mono">{pillars.structure_m15}/25 pts</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '2px' }}>
              <div style={{ width: `${(pillars.structure_m15 / 25) * 100}%`, height: '100%', background: '#a855f7', borderRadius: '2px' }} />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>
              <span>3. Smart Money: Barrido de Liquidez & FVG</span>
              <span className="num-mono">{pillars.smc_liquidity}/25 pts</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '2px' }}>
              <div style={{ width: `${(pillars.smc_liquidity / 25) * 100}%`, height: '100%', background: '#10b981', borderRadius: '2px' }} />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>
              <span>4. Momentum: Histograma MACD & RSI Sano</span>
              <span className="num-mono">{pillars.momentum}/20 pts</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '2px' }}>
              <div style={{ width: `${(pillars.momentum / 20) * 100}%`, height: '100%', background: '#f59e0b', borderRadius: '2px' }} />
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: 'var(--text-secondary)', marginBottom: '3px' }}>
              <span>5. Fuerza ADX + Volumen (sin spread alto)</span>
              <span className="num-mono">{pillars.execution_cost}/15 pts</span>
            </div>
            <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '2px' }}>
              <div style={{ width: `${(pillars.execution_cost / 15) * 100}%`, height: '100%', background: '#64748b', borderRadius: '2px' }} />
            </div>
          </div>

        </div>
      </div>

      {/* Market Environment Filter Status */}
      <div style={{
        background: 'var(--bg-inset)',
        padding: '12px',
        borderRadius: '10px',
        border: '1px solid var(--border-subtle)',
        fontSize: '0.73rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px'
      }}>
        <div style={{ fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Shield size={14} color="#10b981" />
          <span>Filtros de Entorno de Mercado</span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Clock size={12} /> Horario Operativo:
          </span>
          <span style={{ color: selectedSignal?.environment?.session_ok ? '#10b981' : '#f59e0b', fontWeight: 600 }}>
            {selectedSignal?.environment?.session_message ?? 'Sesión activa'}
          </span>
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Globe size={12} /> Noticias de Alto Impacto:
          </span>
          <span style={{ color: selectedSignal?.environment?.news_blocked ? '#ef4444' : '#10b981', fontWeight: 600 }}>
            {selectedSignal?.environment?.news_message ?? 'Sin bloqueos'}
          </span>
        </div>
      </div>

      {/* Real-time Copilot Activity Logs */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
          <Terminal size={14} color="#38bdf8" />
          <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#f8fafc' }}>
            Bitácora en Vivo del Copilot
          </span>
        </div>

        <div style={{
          background: '#04060c',
          padding: '10px',
          borderRadius: '8px',
          border: '1px solid rgba(255, 255, 255, 0.05)',
          maxHeight: '170px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px'
        }}>
          {botLogs.length === 0 ? (
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textAlign: 'center', padding: '12px' }}>
              Esperando eventos del motor de trading...
            </div>
          ) : (
            botLogs.map((log, i) => {
              const badge = getLogBadgeStyle(log.level);
              return (
                <div
                  key={i}
                  style={{
                    fontSize: '0.72rem',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '6px',
                    borderLeft: `2px solid ${badge.text}`,
                    paddingLeft: '6px',
                    lineHeight: '1.3'
                  }}
                >
                  <span className="num-mono" style={{ color: 'var(--text-muted)', fontSize: '0.65rem' }}>
                    [{log.time}]
                  </span>
                  <span style={{
                    fontSize: '0.6rem',
                    fontWeight: 700,
                    padding: '1px 4px',
                    borderRadius: '3px',
                    background: badge.bg,
                    color: badge.text
                  }}>
                    {log.level}
                  </span>
                  <span style={{ color: '#cbd5e1' }}>{log.message}</span>
                </div>
              );
            })
          )}
        </div>
      </div>

    </div>
  );
};
