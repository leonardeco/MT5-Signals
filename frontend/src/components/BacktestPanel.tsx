import React, { useEffect, useState } from 'react';
import type { BacktestResults, BacktestStats } from '../types';
import { apiFetch } from '../api';
import { FlaskConical, Loader2, Play } from 'lucide-react';

const fmtR = (r: number) => `${r >= 0 ? '+' : ''}${r.toFixed(2)}R`;
const rColor = (r: number) => (r > 0 ? '#10b981' : r < 0 ? '#ef4444' : 'var(--text-secondary)');

const StatCell: React.FC<{ st?: BacktestStats }> = ({ st }) => {
  if (!st || st.n === 0) return <td style={{ padding: '6px 8px', color: 'var(--text-muted)' }}>sin operaciones</td>;
  return (
    <td style={{ padding: '6px 8px' }} className="num-mono">
      <div>
        <span style={{ color: rColor(st.total_r), fontWeight: 800 }}>{fmtR(st.total_r)}</span>
        <span style={{ color: 'var(--text-muted)' }}> · {st.n} ops</span>
      </div>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
        {st.win_rate}% acierto · media <span style={{ color: rColor(st.avg_r) }}>{fmtR(st.avg_r)}</span> · PF {st.profit_factor ?? '–'}
      </div>
    </td>
  );
};

// Mismo criterio que history_allows_auto en main.py
const AUTO_MIN_N = 30;
const AUTO_MIN_AVG_R = 0.05;
const AUTO_MIN_T = 2;

const SplitCell: React.FC<{ st?: BacktestStats }> = ({ st }) => {
  const sp = st?.split;
  if (!st || !sp) {
    return <td style={{ padding: '6px 8px', color: 'var(--text-muted)' }}>Sin tramos: recalcula el backtest</td>;
  }
  const t = st.t_stat ?? null;
  const allowed = [sp.antiguo, sp.reciente].every((h) => h.n >= AUTO_MIN_N && h.avg_r >= AUTO_MIN_AVG_R)
    && t !== null && t >= AUTO_MIN_T;
  return (
    <td style={{ padding: '6px 8px', fontSize: '0.7rem' }}>
      <div>
        antes de {sp.cutoff}: <b style={{ color: rColor(sp.antiguo.avg_r) }}>{fmtR(sp.antiguo.avg_r)}</b> ({sp.antiguo.n})
      </div>
      <div>
        después: <b style={{ color: rColor(sp.reciente.avg_r) }}>{fmtR(sp.reciente.avg_r)}</b> ({sp.reciente.n}) · t {t === null ? '—' : t.toFixed(2)}
      </div>
      <div style={{ fontWeight: 700, color: allowed ? '#10b981' : '#f59e0b' }}>
        {allowed ? 'Auto-trading habilitado' : 'Auto-trading bloqueado'}
      </div>
    </td>
  );
};

export const BacktestPanel: React.FC<{ onMessage: (msg: string) => void }> = ({ onMessage }) => {
  const [results, setResults] = useState<BacktestResults | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    apiFetch('/backtest')
      .then((r) => r.json())
      .then((d) => { setResults(d.results); setRunning(d.running); })
      .catch(() => undefined);
  }, []);

  const run = async () => {
    setRunning(true);
    try {
      const res = await apiFetch('/backtest/run?days=180', { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'No se pudo ejecutar el backtest');
      setResults(data.results);
      onMessage('📊 Backtest actualizado con el historial real de MT5');
    } catch (err: any) {
      onMessage(`❌ ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const entries = Object.entries(results?.symbols ?? {});
  const totals = entries.reduce(
    (acc, [, r]) => ({ old: acc.old + (r.anterior?.total_r ?? 0), neu: acc.neu + (r.nuevo?.total_r ?? 0) }),
    { old: 0, neu: 0 },
  );

  return (
    <div className="glass-panel" style={{ padding: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FlaskConical size={18} color="#a855f7" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>Backtest del motor (historial MT5)</h2>
        </div>
        <button
          onClick={run}
          disabled={running}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', borderRadius: '6px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-inset)', color: 'var(--text-secondary)',
            fontSize: '0.75rem', fontWeight: 600,
          }}
        >
          {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
          {running ? 'Calculando (~15 s)…' : 'Recalcular 180 días'}
        </button>
      </div>

      {!results ? (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Aún no hay backtest. Con MT5 conectado, pulsa “Recalcular”.
        </div>
      ) : (
        <>
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '10px' }}>
            Resultados en R netos de costes (spread real de los ticks, deslizamiento y comisión de costs.py; 1R = lo que arriesgas por operación; con 1% de riesgo, −10R ≈ −10% de la cuenta).
            Calculado el {results.generated_at.replace('T', ' ')}. Total anterior{' '}
            <b style={{ color: rColor(totals.old) }}>{fmtR(totals.old)}</b> · total plan nuevo{' '}
            <b style={{ color: rColor(totals.neu) }}>{fmtR(totals.neu)}</b>.
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ padding: '6px 8px' }}>Par</th>
                  <th style={{ padding: '6px 8px' }}>Anterior (mercado, ATR)</th>
                  <th style={{ padding: '6px 8px' }}>Plan nuevo (zona + gatillo)</th>
                  <th style={{ padding: '6px 8px' }} title="Criterio del auto-trading: ambos tramos ≥ +0.05R con ≥ 30 ops cada uno y t ≥ 2">
                    Tramos (nuevo) y auto-trading
                  </th>
                  <th style={{ padding: '6px 8px' }}>Embudo de setups</th>
                </tr>
              </thead>
              <tbody>
                {entries.map(([sym, r]) => (
                  <tr key={sym} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '6px 8px', fontWeight: 700 }}>
                      {sym}
                      <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                        {r.period ? `${r.period.from} → ${r.period.to}` : r.error}
                      </div>
                    </td>
                    <StatCell st={r.anterior} />
                    <StatCell st={r.nuevo} />
                    <SplitCell st={r.nuevo} />
                    <td style={{ padding: '6px 8px', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                      {r.nuevo?.funnel && (
                        <>
                          {r.nuevo.funnel.setups} setups → <b style={{ color: '#10b981' }}>{r.nuevo.funnel.activadas}</b> activadas
                          <div>
                            {r.nuevo.funnel.sin_espacio} sin espacio · {r.nuevo.funnel.invalidadas} invalidadas · {r.nuevo.funnel.expiradas} expiradas
                          </div>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
};
