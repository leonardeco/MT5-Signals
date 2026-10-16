import React, { useEffect, useState } from 'react';
import type { JournalStats, TradeHistoryItem } from '../types';
import { apiFetch } from '../api';
import { BookOpen, RefreshCw, Award, Percent, DollarSign } from 'lucide-react';

export const JournalPanel: React.FC = () => {
  const [history, setHistory] = useState<TradeHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [stats, setStats] = useState<JournalStats | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const [res, st] = await Promise.all([
        apiFetch('/history'),
        apiFetch('/journal/stats'),
      ]);
      if (res.ok) {
        const data = await res.json();
        setHistory(data);
      }
      if (st.ok) setStats(await st.json());
    } catch (err) {
      console.error('Error fetching trade history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  const totalTrades = history.length;
  const closedTrades = history.filter((t) => t.status === 'CLOSED');
  const winningTrades = closedTrades.filter((t) => t.profit > 0);
  const winRate = closedTrades.length > 0 ? (winningTrades.length / closedTrades.length) * 100 : 0;
  const netProfit = closedTrades.reduce((acc, t) => acc + t.profit, 0);
  const fmtR = (r?: number | null) => (r == null ? '—' : `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`);
  const expectancy = stats?.expectancy_r ?? null;

  return (
    <div className="glass-panel" style={{ padding: '18px' }}>
      
      {/* Header and Refresh */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <BookOpen size={18} color="#38bdf8" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>
            Bitácora de operaciones (R, MAE/MFE, vivo vs backtest)
          </h2>
        </div>

        <button
          onClick={fetchHistory}
          disabled={loading}
          style={{
            padding: '5px 12px',
            borderRadius: '6px',
            border: '1px solid var(--border-subtle)',
            background: 'var(--bg-inset)',
            color: 'var(--text-secondary)',
            fontSize: '0.75rem',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          Actualizar
        </button>
      </div>

      {/* KPI Cards Row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '12px',
        marginBottom: '14px'
      }}>
        <div style={{
          background: 'var(--bg-inset)',
          padding: '10px 14px',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}>
          <Award size={18} color="#38bdf8" />
          <div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Operaciones Registradas</div>
            <div className="num-mono" style={{ fontSize: '1.1rem', fontWeight: 800, color: '#f8fafc' }}>
              {totalTrades}
            </div>
          </div>
        </div>

        <div style={{
          background: 'var(--bg-inset)',
          padding: '10px 14px',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}>
          <Percent size={18} color="#10b981" />
          <div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}
                 title="Media de R por plan cerrado (las dos patas de una orden dividida cuentan como un plan)">
              Expectativa ({stats?.n ?? 0} planes) · acierto {winRate.toFixed(0)}%
            </div>
            <div className="num-mono" style={{ fontSize: '1.1rem', fontWeight: 800, color: (expectancy ?? 0) > 0 ? '#10b981' : '#f59e0b' }}>
              {fmtR(expectancy)}
            </div>
          </div>
        </div>

        <div style={{
          background: 'var(--bg-inset)',
          padding: '10px 14px',
          borderRadius: '8px',
          border: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}>
          <DollarSign size={18} color={netProfit >= 0 ? '#10b981' : '#ef4444'} />
          <div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Beneficio Neto Histórico</div>
            <div className="num-mono" style={{ fontSize: '1.1rem', fontWeight: 800, color: netProfit >= 0 ? '#10b981' : '#ef4444' }}>
              {netProfit >= 0 ? '+' : ''}${netProfit.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {stats && stats.n > 0 && (
        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '10px', lineHeight: 1.6 }}>
          <b>Vivo vs backtest (neto):</b>{' '}
          {Object.entries(stats.by_symbol).map(([sym, s]) => (
            <span key={sym} style={{ marginRight: '12px' }}>
              {sym} {fmtR(s.expectancy_r)} en {s.n} vs {fmtR(s.backtest_avg_r)}
            </span>
          ))}
          <div>
            MAE medio {fmtR(stats.avg_mae_r)} · MFE medio {fmtR(stats.avg_mfe_r)}
            {stats.avg_slippage_px != null && <> · deslizamiento medio {stats.avg_slippage_px} (precio, + en contra)</>}
          </div>
        </div>
      )}

      {/* Trades History Table */}
      {history.length === 0 ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Aún no hay operaciones registradas en la base de datos.
        </div>
      ) : (
        <div style={{ maxHeight: '220px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
            <thead>
              <tr style={{ color: 'var(--text-muted)', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)' }}>
                <th style={{ padding: '6px 8px' }}>Ticket</th>
                <th style={{ padding: '6px 8px' }}>Símbolo</th>
                <th style={{ padding: '6px 8px' }}>Dirección</th>
                <th style={{ padding: '6px 8px' }}>Lotaje</th>
                <th style={{ padding: '6px 8px' }}>Entrada</th>
                <th style={{ padding: '6px 8px' }}>Cierre</th>
                <th style={{ padding: '6px 8px' }}>Score</th>
                <th style={{ padding: '6px 8px' }}>Estado</th>
                <th style={{ padding: '6px 8px' }} title="Resultado en R · peor (MAE) / mejor (MFE) excursión">R · MAE/MFE</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>PnL</th>
              </tr>
            </thead>
            <tbody>
              {history.map((t) => {
                const isBuy = t.direction === 'BUY';
                const isProfit = t.profit >= 0;

                return (
                  <tr key={t.id} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.03)' }}>
                    <td className="num-mono" style={{ padding: '8px', color: 'var(--text-muted)' }}>#{t.ticket}</td>
                    <td style={{ padding: '8px', fontWeight: 700, color: '#f8fafc' }}>
                      {t.symbol}
                      {t.leg && t.leg !== 'UNICA' && (
                        <span style={{ marginLeft: '4px', fontSize: '0.6rem', color: 'var(--text-muted)' }}>{t.leg}</span>
                      )}
                    </td>
                    <td style={{ padding: '8px', color: isBuy ? '#10b981' : '#ef4444', fontWeight: 700 }}>{t.direction}</td>
                    <td className="num-mono" style={{ padding: '8px' }}>{t.volume} L</td>
                    <td className="num-mono" style={{ padding: '8px' }}>{t.entry_price}</td>
                    <td className="num-mono" style={{ padding: '8px' }}>{t.close_price ?? '-'}</td>
                    <td className="num-mono" style={{ padding: '8px', color: '#38bdf8' }}>{t.score != null ? `${t.score}/100` : '—'}</td>
                    <td style={{ padding: '8px' }}>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: '4px',
                        fontSize: '0.65rem',
                        fontWeight: 700,
                        background: t.status === 'OPEN' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(100, 116, 139, 0.15)',
                        color: t.status === 'OPEN' ? '#38bdf8' : '#94a3b8'
                      }}>
                        {t.status}
                      </span>
                    </td>
                    <td className="num-mono" style={{ padding: '8px', fontSize: '0.68rem' }}>
                      {fmtR(t.r_multiple)}
                      {t.mae_r != null && (
                        <span style={{ color: 'var(--text-muted)' }}> · {t.mae_r.toFixed(2)}/{(t.mfe_r ?? 0).toFixed(2)}</span>
                      )}
                    </td>
                    <td className="num-mono" style={{ padding: '8px', textAlign: 'right', fontWeight: 700, color: isProfit ? '#10b981' : '#ef4444' }}>
                      {t.status === 'CLOSED' ? `${isProfit ? '+' : ''}$${t.profit.toFixed(2)}` : 'Flotando'}
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
