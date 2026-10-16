import React, { useState } from 'react';
import type { Position } from '../types';
import { apiFetch } from '../api';
import { ShieldCheck, XCircle, AlertOctagon, TrendingUp, TrendingDown } from 'lucide-react';

interface PositionsPanelProps {
  positions: Position[];
  onPositionClosed: (msg: string) => void;
}

export const PositionsPanel: React.FC<PositionsPanelProps> = ({
  positions,
  onPositionClosed
}) => {
  const [closingTicket, setClosingTicket] = useState<number | null>(null);
  const [closingAll, setClosingAll] = useState<boolean>(false);

  const handleClose = async (ticket: number) => {
    setClosingTicket(ticket);
    try {
      const res = await apiFetch(`/close/${ticket}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Error al cerrar posición');
      onPositionClosed(`Posición #${ticket} cerrada exitosamente`);
    } catch (err: any) {
      onPositionClosed(`Error: ${err.message}`);
    } finally {
      setClosingTicket(null);
    }
  };

  const handleCloseAll = async () => {
    if (!window.confirm('¿Cerrar todas las posiciones abiertas por el bot? Las operaciones manuales y de otros EAs no se tocan.')) return;
    setClosingAll(true);
    try {
      const res = await apiFetch('/close-all', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Error al cerrar posiciones');
      onPositionClosed(`Cierre de emergencia: ${data.closed_positions} posiciones del bot liquidadas`);
    } catch (err: any) {
      onPositionClosed(`Error: ${err.message}`);
    } finally {
      setClosingAll(false);
    }
  };

  const totalFloating = positions.reduce((acc, p) => acc + p.profit, 0);

  return (
    <div className="glass-panel" style={{ padding: '18px' }}>
      
      {/* Header with Stats and Emergency Close All */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>
            Posiciones Abiertas en MT5 ({positions.length})
          </h2>
          {positions.length > 0 && (
            <span className="num-mono" style={{
              fontSize: '0.85rem',
              fontWeight: 700,
              color: totalFloating >= 0 ? '#10b981' : '#ef4444'
            }}>
              PnL: {totalFloating >= 0 ? '+' : ''}${totalFloating.toFixed(2)}
            </span>
          )}
        </div>

        {positions.length > 0 && (
          <button
            onClick={handleCloseAll}
            disabled={closingAll}
            style={{
              padding: '6px 14px',
              borderRadius: '8px',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              background: 'rgba(239, 68, 68, 0.15)',
              color: '#ef4444',
              fontSize: '0.75rem',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <AlertOctagon size={14} />
            {closingAll ? 'Cerrando...' : 'Cerrar posiciones del bot'}
          </button>
        )}
      </div>

      {/* Positions Table */}
      {positions.length === 0 ? (
        <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No hay órdenes abiertas en el mercado actualmente.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.78rem' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)' }}>
                <th style={{ padding: '8px 10px' }}>Ticket</th>
                <th style={{ padding: '8px 10px' }}>Símbolo</th>
                <th style={{ padding: '8px 10px' }}>Tipo</th>
                <th style={{ padding: '8px 10px' }}>Lotaje</th>
                <th style={{ padding: '8px 10px' }}>Entrada</th>
                <th style={{ padding: '8px 10px' }}>Actual</th>
                <th style={{ padding: '8px 10px' }}>SL / TP</th>
                <th style={{ padding: '8px 10px' }}>Flotante</th>
                <th style={{ padding: '8px 10px' }}>Protección</th>
                <th style={{ padding: '8px 10px', textAlign: 'right' }}>Acción</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const isBuy = p.type === 'BUY';
                const isProfitPos = p.profit >= 0;

                return (
                  <tr
                    key={p.ticket}
                    style={{
                      borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
                      transition: 'background 0.2s ease',
                    }}
                  >
                    <td className="num-mono" style={{ padding: '10px', color: 'var(--text-muted)' }}>
                      #{p.ticket}
                    </td>

                    <td style={{ padding: '10px', fontWeight: 700, color: '#f8fafc' }}>
                      {p.symbol}
                    </td>

                    <td style={{ padding: '10px' }}>
                      <span style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.68rem',
                        fontWeight: 700,
                        background: isBuy ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                        color: isBuy ? '#10b981' : '#ef4444'
                      }}>
                        {isBuy ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                        {p.type}
                      </span>
                    </td>

                    <td className="num-mono" style={{ padding: '10px', fontWeight: 600 }}>
                      {p.volume} L
                    </td>

                    <td className="num-mono" style={{ padding: '10px', color: '#cbd5e1' }}>
                      {p.price_open}
                    </td>

                    <td className="num-mono" style={{ padding: '10px', color: '#cbd5e1' }}>
                      {p.price_current}
                    </td>

                    <td className="num-mono" style={{ padding: '10px', fontSize: '0.72rem' }}>
                      <span style={{ color: '#ef4444' }}>{p.sl > 0 ? p.sl : '-'}</span> /{' '}
                      <span style={{ color: '#10b981' }}>{p.tp > 0 ? p.tp : '-'}</span>
                    </td>

                    <td className="num-mono" style={{ padding: '10px', fontWeight: 800, color: isProfitPos ? '#10b981' : '#ef4444' }}>
                      {isProfitPos ? '+' : ''}${p.profit.toFixed(2)}
                    </td>

                    <td style={{ padding: '10px' }}>
                      {p.is_breakeven ? (
                        <span style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontSize: '0.65rem',
                          fontWeight: 700,
                          background: 'rgba(56, 189, 248, 0.15)',
                          color: '#38bdf8'
                        }}>
                          <ShieldCheck size={12} /> BE Protegido
                        </span>
                      ) : (
                        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                          En riesgo 1R
                        </span>
                      )}
                    </td>

                    <td style={{ padding: '10px', textAlign: 'right' }}>
                      <button
                        onClick={() => handleClose(p.ticket)}
                        disabled={closingTicket === p.ticket}
                        title="Cerrar esta posición ahora"
                        style={{
                          padding: '4px 10px',
                          borderRadius: '6px',
                          border: 'none',
                          background: 'rgba(239, 68, 68, 0.2)',
                          color: '#ef4444',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px'
                        }}
                      >
                        <XCircle size={12} />
                        {closingTicket === p.ticket ? '...' : 'Cerrar'}
                      </button>
                    </td>

                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

    </div>
  );
};
