import React, { useEffect, useRef, useState } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  LineStyle,
} from 'lightweight-charts';
import type {
  IChartApi,
  ISeriesApi,
  CandlestickData,
  LineData,
  Time
} from 'lightweight-charts';
import type { TradingSignal } from '../types';
import { apiFetch, wsUrl } from '../api';

interface ChartProps {
  symbol: string;
  activeSignal?: TradingSignal;
  onSelectSymbol: (sym: string) => void;
  watchlist: string[];
}

export const LightweightChart: React.FC<ChartProps> = ({
  symbol,
  activeSignal,
  onSelectSymbol,
  watchlist
}) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const ema21SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const ema200SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const priceLinesRef = useRef<any[]>([]);

  const [timeframe, setTimeframe] = useState<string>('M15');
  const [loading, setLoading] = useState<boolean>(true);
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [simulated, setSimulated] = useState<boolean>(false);

  // 1. Initialize Lightweight Chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    chartContainerRef.current.innerHTML = '';

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#090e1a' },
        textColor: '#94a3b8',
        fontFamily: "'JetBrains Mono', monospace"
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        autoScale: true,
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
        secondsVisible: false,
      },
      width: chartContainerRef.current.clientWidth,
      height: 480,
    });

    chartInstanceRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });
    candleSeriesRef.current = candleSeries;

    const ema21 = chart.addSeries(LineSeries, {
      color: '#38bdf8',
      lineWidth: 2,
      title: 'EMA 21',
    });
    ema21SeriesRef.current = ema21;

    const ema50 = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 2,
      title: 'EMA 50',
    });
    ema50SeriesRef.current = ema50;

    const ema200 = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
      title: 'EMA 200',
    });
    ema200SeriesRef.current = ema200;

    const handleResize = () => {
      if (chartContainerRef.current && chartInstanceRef.current) {
        chartInstanceRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // 1b. Decimales del eje según el símbolo (por defecto mostraba 2: GBPUSD salía como "1.32")
  useEffect(() => {
    const precision = symbol.includes('JPY') ? 3 : symbol.includes('US100') || symbol.includes('XAU') ? 2 : 5;
    const priceFormat = { type: 'price' as const, precision, minMove: 1 / 10 ** precision };
    [candleSeriesRef, ema21SeriesRef, ema50SeriesRef, ema200SeriesRef].forEach((ref) => ref.current?.applyOptions({ priceFormat }));
  }, [symbol]);

  // 2. Fetch Historical Candles on Symbol or Timeframe change
  useEffect(() => {
    let isMounted = true;
    setLoading(true);

    const applyCandles = (data: { candles?: { close: number }[]; simulated?: boolean; ema21?: unknown; ema50?: unknown; ema200?: unknown }, fit: boolean) => {
      if (!isMounted) return;
      setSimulated(Boolean(data.simulated));
      if (candleSeriesRef.current && ema21SeriesRef.current && ema50SeriesRef.current && ema200SeriesRef.current && data.candles) {
        candleSeriesRef.current.setData(data.candles as CandlestickData<Time>[]);
        ema21SeriesRef.current.setData((data.ema21 ?? []) as LineData<Time>[]);
        ema50SeriesRef.current.setData((data.ema50 ?? []) as LineData<Time>[]);
        ema200SeriesRef.current.setData((data.ema200 ?? []) as LineData<Time>[]);
        if (data.candles.length > 0) setLastPrice(data.candles[data.candles.length - 1].close);
        if (fit) chartInstanceRef.current?.timeScale().fitContent();
      }
      setLoading(false);
    };

    const fetchHistorical = async (fit: boolean) => {
      try {
        const res = await apiFetch(`/candles/${symbol}?tf=${timeframe}&bars=250`);
        if (!res.ok) throw new Error('Failed to fetch candles');
        applyCandles(await res.json(), fit);
      } catch (err) {
        console.error('Error fetching candles:', err);
        if (isMounted) setLoading(false);
      }
    };

    fetchHistorical(true);

    let wsOpen = false;
    const ws = new WebSocket(wsUrl(`/ws/chart/${symbol}?tf=${timeframe}`));
    ws.onopen = () => { wsOpen = true; };
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'TICK_BAR' && candleSeriesRef.current) {
          candleSeriesRef.current.update(payload.candle as CandlestickData<Time>);
          ema21SeriesRef.current?.update(payload.ema21 as LineData<Time>);
          ema50SeriesRef.current?.update(payload.ema50 as LineData<Time>);
          ema200SeriesRef.current?.update(payload.ema200 as LineData<Time>);
          setLastPrice(payload.candle.close);
          setSimulated(Boolean(payload.simulated));
        }
      } catch (err) {
        console.error('WebSocket chart parse error:', err);
      }
    };
    ws.onerror = () => { wsOpen = false; };
    ws.onclose = () => { wsOpen = false; };

    const poll = window.setInterval(() => {
      if (!wsOpen) fetchHistorical(false);
    }, 2000);

    return () => {
      isMounted = false;
      window.clearInterval(poll);
      ws.close();
    };
  }, [symbol, timeframe]);

  // 3. Update Price Lines for Active Signal
  useEffect(() => {
    if (!candleSeriesRef.current) return;

    priceLinesRef.current.forEach((line) => {
      try {
        candleSeriesRef.current?.removePriceLine(line);
      } catch {
        // ignore
      }
    });
    priceLinesRef.current = [];

    if (activeSignal && activeSignal.direction !== 'NEUTRAL') {
      const series = candleSeriesRef.current;
      const addLine = (price: number | undefined, color: string, title: string, style: LineStyle, width: 1 | 2 = 2) => {
        if (!price || price <= 0) return;
        priceLinesRef.current.push(series.createPriceLine({
          price, color, lineWidth: width, lineStyle: style, axisLabelVisible: true, title,
        }));
      };
      const hasPlan = activeSignal.state && activeSignal.state !== 'SIN_SETUP';

      if (hasPlan && activeSignal.entry_type !== 'MERCADO') {
        addLine(activeSignal.zone_high, '#38bdf8', 'ZONA', LineStyle.Dashed);
        addLine(activeSignal.zone_low, '#38bdf8', 'ZONA', LineStyle.Dashed);
      } else {
        addLine(activeSignal.entry_price, '#38bdf8', `ENTRADA ${activeSignal.direction}`, LineStyle.Dashed);
      }
      addLine(activeSignal.sl, '#ef4444', 'SL', LineStyle.Dotted);
      if (hasPlan) {
        addLine(activeSignal.tp1, '#10b981', `TP1 ${activeSignal.rr_tp1 ?? ''}R`, LineStyle.Dotted);
        addLine(activeSignal.tp, '#34d399', `TP2 ${activeSignal.rr_tp2 ?? ''}R`, LineStyle.Dotted);
        // Niveles de liquidez cercanos (los que el plan usa como objetivos u obstáculos)
        (activeSignal.levels ?? []).forEach((lv) => addLine(lv.price, 'rgba(148, 163, 184, 0.55)', lv.name, LineStyle.SparseDotted, 1));
      } else {
        addLine(activeSignal.tp, '#10b981', 'TP', LineStyle.Dotted);
      }
    }
  }, [activeSignal, symbol]);

  return (
    <div className="glass-panel" style={{ padding: '18px', overflow: 'hidden' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '12px',
        marginBottom: '14px',
        paddingBottom: '12px',
        borderBottom: '1px solid var(--border-subtle)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {watchlist.map((sym) => {
            const isSelected = sym === symbol;
            return (
              <button
                key={sym}
                onClick={() => onSelectSymbol(sym)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '8px',
                  border: isSelected ? '1px solid #38bdf8' : '1px solid var(--border-subtle)',
                  background: isSelected ? 'rgba(56, 189, 248, 0.15)' : 'var(--bg-inset)',
                  color: isSelected ? '#38bdf8' : 'var(--text-secondary)',
                  fontWeight: 700,
                  fontSize: '0.8rem',
                  letterSpacing: '0.02em',
                }}
              >
                {sym}
              </button>
            );
          })}
        </div>

        {lastPrice !== null && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '0.75rem', color: simulated ? '#ef4444' : 'var(--text-muted)', fontWeight: simulated ? 700 : 400 }}>
              {simulated ? 'PRECIO SIMULADO (NO REAL):' : 'PRECIO EN VIVO:'}
            </span>
            <span className="num-mono" style={{ fontSize: '1.15rem', fontWeight: 800, color: simulated ? '#ef4444' : '#f8fafc', textDecoration: simulated ? 'line-through' : 'none' }}>
              {lastPrice.toFixed(symbol.includes('JPY') ? 3 : symbol.includes('US100') || symbol.includes('XAU') ? 2 : 5)}
            </span>
          </div>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-inset)', padding: '3px', borderRadius: '8px' }}>
            {['M1', 'M5', 'M15', 'H1', 'H4', 'D1'].map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                style={{
                  padding: '4px 10px',
                  borderRadius: '6px',
                  border: 'none',
                  background: timeframe === tf ? '#2563eb' : 'transparent',
                  color: timeframe === tf ? '#ffffff' : 'var(--text-muted)',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                }}
              >
                {tf}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: '10px', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#38bdf8' }} /> EMA 21
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#f59e0b' }} /> EMA 50
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#a855f7' }} /> EMA 200
            </span>
          </div>
        </div>
      </div>

      <div style={{ position: 'relative', width: '100%', borderRadius: '10px', overflow: 'hidden' }}>
        {loading && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(9, 14, 26, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10,
            color: '#38bdf8',
            fontSize: '0.85rem',
            fontWeight: 600,
          }}>
            Cargando velas institucionales de {symbol}...
          </div>
        )}
        {simulated && !loading && (
          <div style={{
            position: 'absolute',
            top: '12px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 9,
            padding: '6px 14px',
            borderRadius: '8px',
            background: 'rgba(239, 68, 68, 0.9)',
            color: '#ffffff',
            fontSize: '0.8rem',
            fontWeight: 700,
            pointerEvents: 'none',
          }}>
            ⚠️ VELAS SIMULADAS — MT5 desconectado, no reflejan el mercado real
          </div>
        )}
        <div ref={chartContainerRef} style={{ width: '100%', height: '480px' }} />
      </div>
    </div>
  );
};
