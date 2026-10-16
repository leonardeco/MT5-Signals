import React, { useEffect, useState } from 'react';
import { Loader2, Play, Snowflake } from 'lucide-react';
import { apiFetch } from '../api';

interface ForwardStrategy {
  n: number;
  avg_r?: number | null;
  t_stat?: number | null;
  ic95_media?: [number, number] | null;
  esperado_r: number;
  abiertas_sin_terminar?: number;
  por_simbolo: Record<string, { n: number; avg_r: number }>;
}

interface ShadowPosition {
  direccion: 'BUY' | 'SELL';
  desde: string;
  entrada: number;
  sesiones_restantes: number;
}

interface ForwardResponse {
  running: boolean;
  config: { congelado: string } | null;
  results: {
    generado: string;
    congelado: string;
    reglas_modificadas: string[];
    MOTOR: ForwardStrategy;
    'H-B': ForwardStrategy;
    'H-B_posiciones_en_sombra': Record<string, ShadowPosition>;
  } | null;
}

const fmtR = (r?: number | null) => (r == null ? '—' : `${r >= 0 ? '+' : ''}${r.toFixed(3)}R`);
const rColor = (r?: number | null) => ((r ?? 0) > 0 ? '#10b981' : (r ?? 0) < 0 ? '#ef4444' : 'var(--text-secondary)');

const LABELS: Record<string, string> = {
  MOTOR: 'Motor de señales (intradía)',
  'H-B': 'H-B tendencia 12 meses (D1)',
};

export const ForwardPanel: React.FC<{ onMessage: (msg: string) => void }> = ({ onMessage }) => {
  const [data, setData] = useState<ForwardResponse | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    apiFetch('/forward')
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  const run = async () => {
    setRunning(true);
    try {
      const res = await apiFetch('/forward/run', { method: 'POST' });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'No se pudo calcular');
      setData(body);
      onMessage('🧪 Prueba a futuro actualizada');
    } catch (err: any) {
      onMessage(`❌ ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const r = data?.results;
  const changed = r?.reglas_modificadas ?? [];

  return (
    <div className="glass-panel" style={{ padding: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Snowflake size={18} color="#38bdf8" />
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>Prueba a futuro en sombra (sin operar)</h2>
        </div>
        <button
          onClick={run}
          disabled={running || !data?.config}
          style={{
            display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', borderRadius: '6px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-inset)', color: 'var(--text-secondary)',
            fontSize: '0.75rem', fontWeight: 600,
          }}
        >
          {running ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
          {running ? 'Calculando…' : 'Actualizar'}
        </button>
      </div>

      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '10px', lineHeight: 1.5 }}>
        Reglas congeladas el {data?.config?.congelado?.slice(0, 10) ?? '— (sin congelar: python forward.py freeze)'}.
        Solo cuentan datos posteriores, netos de costes: es la única prueba sin sesgo de los 22 intentos del laboratorio.
        Ninguna orden se envía; deja que se acumulen al menos 3 meses antes de sacar conclusiones.
        {r && <> Calculado el {r.generado.replace('T', ' ').slice(0, 16)}.</>}
      </div>

      {changed.length > 0 && (
        <div style={{ fontSize: '0.72rem', color: '#fca5a5', marginBottom: '10px' }}>
          ⚠️ Las reglas cambiaron después de congelar ({changed.join(', ')}): este resultado ya no es una prueba limpia.
        </div>
      )}

      {!r ? (
        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Aún no hay cálculo. Con MT5 conectado, pulsa “Actualizar”.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.75rem' }}>
          <thead>
            <tr style={{ color: 'var(--text-muted)', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '6px 8px' }}>Estrategia</th>
              <th style={{ padding: '6px 8px' }}>Operaciones</th>
              <th style={{ padding: '6px 8px' }}>Media neta (esperada)</th>
              <th style={{ padding: '6px 8px' }}>t · IC95</th>
              <th style={{ padding: '6px 8px' }}>Por símbolo</th>
            </tr>
          </thead>
          <tbody>
            {(['MOTOR', 'H-B'] as const).map((k) => {
              const s = r[k];
              return (
                <tr key={k} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '6px 8px', fontWeight: 700 }}>{LABELS[k]}</td>
                  <td className="num-mono" style={{ padding: '6px 8px' }}>
                    {s.n}
                    {!!s.abiertas_sin_terminar && <span style={{ color: 'var(--text-muted)' }}> (+{s.abiertas_sin_terminar} en curso)</span>}
                  </td>
                  <td className="num-mono" style={{ padding: '6px 8px' }}>
                    <b style={{ color: rColor(s.avg_r) }}>{fmtR(s.avg_r)}</b>
                    <span style={{ color: 'var(--text-muted)' }}> ({fmtR(s.esperado_r)})</span>
                  </td>
                  <td className="num-mono" style={{ padding: '6px 8px', color: 'var(--text-muted)' }}>
                    {s.t_stat ?? '—'} · {s.ic95_media ? `${fmtR(s.ic95_media[0])} … ${fmtR(s.ic95_media[1])}` : '—'}
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                    {Object.entries(s.por_simbolo).map(([sym, x]) => `${sym} ${fmtR(x.avg_r)} (${x.n})`).join(' · ') || '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {r && Object.keys(r['H-B_posiciones_en_sombra']).length > 0 && (
        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '10px' }}>
          <b>H-B en sombra ahora</b> (señal informativa, no se opera):{' '}
          {Object.entries(r['H-B_posiciones_en_sombra']).map(([sym, p]) => (
            <span key={sym} style={{ marginRight: '12px' }}>
              {sym} <span style={{ color: p.direccion === 'BUY' ? '#10b981' : '#ef4444', fontWeight: 700 }}>{p.direccion}</span>{' '}
              desde {p.desde} @ {p.entrada} · quedan {p.sesiones_restantes} sesiones
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
