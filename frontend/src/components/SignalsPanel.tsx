import React, { useState } from 'react';
import type { TradingSignal } from '../types';
import { apiFetch } from '../api';
import { ArrowUpRight, ArrowDownRight, Minus, CheckCircle, Send, Loader2, AlertTriangle } from 'lucide-react';

const STATE_META: Record<string, { label: string; color: string; hint: string }> = {
  PREPARANDO: { label: 'PREPARANDO', color: '#38bdf8', hint: 'Esperando que el precio llegue a la zona' },
  EN_ZONA: { label: 'EN ZONA', color: '#f59e0b', hint: 'Precio en la zona: esperando gatillo en M5' },
  ACTIVADA: { label: 'ACTIVADA', color: '#10b981', hint: 'Gatillo confirmado: entrada a mercado ahora' },
  EXPIRADA: { label: 'EXPIRADA', color: '#64748b', hint: 'Ventana de entrada cerrada' },
  INVALIDADA: { label: 'INVALIDADA', color: '#ef4444', hint: 'El precio rompió el nivel de invalidación' },
  DESCARTADA: { label: 'DESCARTADA', color: '#a855f7', hint: 'El plan no cumple las reglas de riesgo' },
};

const fmtCountdown = (secs?: number) => {
  if (!secs || secs <= 0) return '';
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const fmtR = (r: number) => `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`;
const rColor = (r?: number) => ((r ?? 0) > 0 ? '#10b981' : '#ef4444');

// Mismo criterio que history_allows_auto en main.py
const EDGE_RULE = 'ambos tramos del backtest ≥ +0.05R con ≥ 30 ops cada uno y t ≥ 2';

interface SignalsPanelProps {
  signals: TradingSignal[];
  selectedSymbol: string;
  onSelectSymbol: (symbol: string) => void;
  onOrderExecuted: (msg: string) => void;
}

export const SignalsPanel: React.FC<SignalsPanelProps> = ({
  signals,
  selectedSymbol,
  onSelectSymbol,
  onOrderExecuted
}) => {
  const [executing, setExecuting] = useState<string | null>(null);
  const liveSignals = signals.some((s) => s.data_source === 'MT5');
  const anyEdge = signals.some((s) => s.auto_eligible);

  const handleExecute = async (sig: TradingSignal, e: React.MouseEvent) => {
    e.stopPropagation();
    if (sig.direction === 'NEUTRAL') return;
    if (!sig.auto_eligible && !window.confirm(
      `${sig.symbol} no tiene ventaja demostrada en el backtest (${EDGE_RULE}).\n` +
      'La señal es lectura de contexto, no una recomendación. ¿Ejecutar igualmente?'
    )) return;

    setExecuting(sig.symbol);
    try {
      const res = await apiFetch('/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: sig.symbol,
          direction: sig.direction,
          volume: sig.recommended_lot,
          sl: sig.sl,
          tp: sig.tp,
          tp1: sig.tp1 ?? null,
          score: sig.score
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Fallo al ejecutar orden');
      onOrderExecuted(
        `✅ Orden ejecutada: Ticket #${data.ticket} en ${sig.symbol} @ ${data.executed_price} (${data.volume} L)` +
        (data.risk_note ? ` · ${data.risk_note}` : '')
      );
    } catch (err: any) {
      onOrderExecuted(`❌ Error al ejecutar: ${err.message}`);
    } finally {
      setExecuting(null);
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span>📡 Radar de Señales Cuantitativas</span>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 500 }}>
            (Escaneo cada 1.5s)
          </span>
        </h2>
      </div>

      {liveSignals && !anyEdge && (
        <div style={{
          display: 'flex', gap: '8px', alignItems: 'flex-start', marginBottom: '12px', padding: '10px 12px',
          borderRadius: '8px', fontSize: '0.74rem', lineHeight: 1.45, color: '#fcd34d',
          background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.3)',
        }}>
          <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
          <span>
            <strong>Ningún par tiene ventaja estadística demostrada.</strong> El backtest no muestra ganancia robusta
            ({EDGE_RULE}), y un score más alto no predijo mejores resultados. Usa las señales como lectura de
            contexto; el auto-trading permanece bloqueado.
          </span>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {signals.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Escaneando mercado con MetaTrader 5...
          </div>
        ) : (
          signals.map((sig) => {
            const isSelected = sig.symbol === selectedSymbol;
            const isBuy = sig.direction === 'BUY';
            const isSell = sig.direction === 'SELL';
            const isNeutral = sig.direction === 'NEUTRAL';

            // Color neutro: el score no ordena la calidad de las señales en el backtest
            const scoreColor = '#cbd5e1';

            return (
              <div
                key={sig.symbol}
                onClick={() => onSelectSymbol(sig.symbol)}
                style={{
                  background: isSelected ? 'var(--bg-card-hover)' : 'var(--bg-inset)',
                  border: isSelected
                    ? '1px solid rgba(56, 189, 248, 0.4)'
                    : '1px solid var(--border-subtle)',
                  borderLeft: isBuy
                    ? '4px solid #10b981'
                    : isSell
                    ? '4px solid #ef4444'
                    : '4px solid #64748b',
                  borderRadius: '10px',
                  padding: '14px 16px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: isSelected ? '0 4px 16px rgba(0, 0, 0, 0.4)' : 'none'
                }}
              >
                {/* Header row: Symbol, Direction Badge, Score */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '1.1rem', fontWeight: 800, color: '#ffffff' }}>
                      {sig.symbol}
                    </span>

                    <span
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '3px 8px',
                        borderRadius: '6px',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        background: isBuy
                          ? 'rgba(16, 185, 129, 0.15)'
                          : isSell
                          ? 'rgba(239, 68, 68, 0.15)'
                          : 'rgba(100, 116, 139, 0.15)',
                        color: isBuy ? '#10b981' : isSell ? '#ef4444' : '#94a3b8',
                        border: isBuy
                          ? '1px solid rgba(16, 185, 129, 0.3)'
                          : isSell
                          ? '1px solid rgba(239, 68, 68, 0.3)'
                          : '1px solid rgba(100, 116, 139, 0.3)',
                      }}
                    >
                      {isBuy && <ArrowUpRight size={13} />}
                      {isSell && <ArrowDownRight size={13} />}
                      {isNeutral && <Minus size={13} />}
                      {sig.direction}
                    </span>

                    {sig.bot_approved && (
                      <span
                        title="Supera el score mínimo del modo elegido. En el backtest el score no predijo mejores resultados."
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '3px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '0.65rem',
                          fontWeight: 700,
                          background: 'rgba(16, 185, 129, 0.2)',
                          color: '#34d399',
                          border: '1px solid rgba(52, 211, 153, 0.4)'
                        }}
                      >
                        <CheckCircle size={10} />
                        SCORE ≥ MODO
                      </span>
                    )}
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div className="num-mono" style={{ fontSize: '1rem', fontWeight: 800, color: scoreColor }}>
                      {sig.score}<span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>/100</span>
                    </div>
                    <div style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
                      score técnico
                    </div>
                  </div>
                </div>

                {/* Score Progress Bar */}
                <div style={{ width: '100%', height: '4px', background: 'rgba(255, 255, 255, 0.06)', borderRadius: '2px', overflow: 'hidden', marginBottom: '10px' }}>
                  <div
                    style={{
                      width: `${sig.score}%`,
                      height: '100%',
                      background: isBuy
                        ? 'linear-gradient(90deg, #059669, #10b981)'
                        : isSell
                        ? 'linear-gradient(90deg, #dc2626, #ef4444)'
                        : '#64748b',
                      borderRadius: '2px',
                      transition: 'width 0.3s ease'
                    }}
                  />
                </div>

                {/* Plan de entrada: estado, zona, SL y objetivos por estructura */}
                {!isNeutral && sig.state && sig.state !== 'SIN_SETUP' && (() => {
                  const meta = STATE_META[sig.state] ?? STATE_META.PREPARANDO;
                  const countdown = fmtCountdown(sig.expires_in);
                  return (
                    <div style={{ marginBottom: '10px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '8px' }}>
                        <span style={{
                          padding: '3px 8px', borderRadius: '6px', fontSize: '0.68rem', fontWeight: 800, letterSpacing: '0.04em',
                          color: meta.color, background: `${meta.color}22`, border: `1px solid ${meta.color}55`,
                        }}>
                          {meta.label}
                        </span>
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', textAlign: 'right' }}>
                          {sig.state_reason || meta.hint}
                          {countdown && <span className="num-mono" style={{ marginLeft: '6px', color: '#cbd5e1' }}>⏱ {countdown}</span>}
                        </span>
                      </div>

                      <div style={{
                        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px 10px', padding: '8px 10px',
                        background: 'rgba(0, 0, 0, 0.25)', borderRadius: '8px', fontSize: '0.72rem',
                      }}>
                        <div style={{ gridColumn: 'span 2' }}>
                          <div style={{ color: 'var(--text-muted)' }}>
                            {sig.entry_type === 'MERCADO' ? 'Entrada (mercado)' : 'Zona de entrada'}
                          </div>
                          <div className="num-mono" style={{ fontWeight: 700, color: '#f8fafc' }}>
                            {sig.entry_type === 'MERCADO' ? sig.entry_price : `${sig.zone_low} – ${sig.zone_high}`}
                          </div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-muted)' }}>Lote (1%)</div>
                          <div className="num-mono" style={{ fontWeight: 800, color: '#38bdf8' }}>{sig.recommended_lot} L</div>
                        </div>
                        <div>
                          <div style={{ color: 'var(--text-muted)' }}>Stop Loss</div>
                          <div className="num-mono" style={{ fontWeight: 700, color: '#ef4444' }}>{sig.sl}</div>
                        </div>
                        <div title={sig.tp1_label}>
                          <div style={{ color: 'var(--text-muted)' }}>TP1 50% ({sig.rr_tp1}R)</div>
                          <div className="num-mono" style={{ fontWeight: 700, color: '#10b981' }}>{sig.tp1}</div>
                        </div>
                        <div title={sig.tp2_label}>
                          <div style={{ color: 'var(--text-muted)' }}>TP2 ({sig.rr_tp2}R)</div>
                          <div className="num-mono" style={{ fontWeight: 700, color: '#34d399' }}>{sig.tp}</div>
                        </div>
                      </div>
                      <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                        TP1: {sig.tp1_label} · TP2: {sig.tp2_label} · tras TP1 el stop pasa a breakeven
                      </div>
                    </div>
                  );
                })()}

                {/* Resultado histórico del mismo tipo de señal */}
                {!isNeutral && sig.history && (
                  <div style={{
                    fontSize: '0.68rem', marginBottom: '10px', padding: '6px 8px', borderRadius: '6px',
                    background: 'rgba(255,255,255,0.03)', color: 'var(--text-secondary)',
                  }}>
                    📊 Backtest {sig.history.period?.from} → {sig.history.period?.to}: par{' '}
                    <span style={{ color: rColor(sig.history.symbol_avg_r), fontWeight: 700 }}>
                      {fmtR(sig.history.symbol_avg_r)}
                    </span> en {sig.history.symbol_n} ops
                    {sig.history.symbol_t_stat != null && <> (t {sig.history.symbol_t_stat.toFixed(2)})</>}
                    {sig.history.old_n != null && sig.history.recent_n != null && (
                      <div style={{ marginTop: '2px' }}>
                        tramo antiguo <span style={{ color: rColor(sig.history.old_avg_r), fontWeight: 700 }}>
                          {fmtR(sig.history.old_avg_r ?? 0)}</span> ({sig.history.old_n}) · reciente{' '}
                        <span style={{ color: rColor(sig.history.recent_avg_r), fontWeight: 700 }}>
                          {fmtR(sig.history.recent_avg_r ?? 0)}</span> ({sig.history.recent_n})
                      </div>
                    )}
                    {sig.auto_eligible === false && (
                      <div style={{ color: '#f59e0b', marginTop: '2px' }}>
                        Auto-trading bloqueado en este par: no cumple {EDGE_RULE}
                      </div>
                    )}
                  </div>
                )}

                {/* Confluence Reasons Tags */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '12px' }}>
                  {sig.reasons.slice(0, 3).map((r, i) => (
                    <div key={i} style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ color: isBuy ? '#10b981' : isSell ? '#ef4444' : '#64748b' }}>•</span>
                      <span>{r}</span>
                    </div>
                  ))}
                </div>

                {/* Action Row */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '8px', borderTop: '1px solid rgba(255, 255, 255, 0.05)' }}>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    Spread: <span className="num-mono" style={{ color: '#cbd5e1' }}>{sig.spread_points} pts</span>
                    {sig.environment?.news_blocked && (
                      <span style={{ marginLeft: '8px', color: '#f59e0b' }} title={sig.environment.news_message}>
                        {sig.environment.calendar_ok === false ? '⚠️ Sin calendario' : '⚠️ Noticia'}
                      </span>
                    )}
                  </div>

                  {!isNeutral && !sig.executable && (
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {sig.state === 'EN_ZONA' ? 'Esperando gatillo M5…' : sig.state === 'PREPARANDO' ? 'Esperando la zona…' : 'No operar'}
                    </span>
                  )}

                  {!isNeutral && sig.executable && (
                    <button
                      onClick={(e) => handleExecute(sig, e)}
                      disabled={executing === sig.symbol}
                      style={{
                        padding: '6px 14px',
                        borderRadius: '6px',
                        border: 'none',
                        background: isBuy
                          ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)'
                          : 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                        color: '#ffffff',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        boxShadow: isBuy
                          ? '0 2px 8px rgba(16, 185, 129, 0.3)'
                          : '0 2px 8px rgba(239, 68, 68, 0.3)'
                      }}
                    >
                      {executing === sig.symbol ? (
                        <>
                          <Loader2 size={12} className="animate-spin" />
                          Enviando...
                        </>
                      ) : (
                        <>
                          <Send size={12} />
                          Ejecutar {sig.direction} ({sig.recommended_lot} L)
                        </>
                      )}
                    </button>
                  )}
                </div>

              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
