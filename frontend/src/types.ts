export interface Pillars {
  macro_h1: number;
  structure_m15: number;
  smc_liquidity: number;
  momentum: number;
  execution_cost: number;
}

export interface Environment {
  allowed: boolean;
  session_ok: boolean;
  session_message: string;
  news_blocked: boolean;
  news_message: string;
  calendar_ok?: boolean;
  correlation_ok: boolean;
  correlation_message: string;
}

export type SignalState =
  | 'SIN_SETUP' | 'PREPARANDO' | 'EN_ZONA' | 'ACTIVADA' | 'EXPIRADA' | 'INVALIDADA' | 'DESCARTADA';

export interface SignalHistory {
  period?: { from: string; to: string };
  bucket: string;
  bucket_n: number;
  bucket_win_rate: number;
  bucket_avg_r: number;
  symbol_n: number;
  symbol_win_rate: number;
  symbol_avg_r: number;
  symbol_profit_factor: number | null;
  symbol_t_stat?: number | null;
  old_n?: number;
  old_avg_r?: number;
  recent_n?: number;
  recent_avg_r?: number;
}

export interface BacktestStats {
  n: number;
  win_rate: number;
  avg_r: number;
  total_r: number;
  profit_factor: number | null;
  max_losing_streak: number;
  t_stat?: number | null;
  by_bucket?: Record<string, BacktestStats>;
  funnel?: Record<string, number>;
  split?: { cutoff: string; antiguo: BacktestStats; reciente: BacktestStats };
}

export interface BacktestSymbolResult {
  error?: string;
  broker_symbol?: string;
  period?: { from: string; to: string };
  nuevo?: BacktestStats;
  anterior?: BacktestStats;
}

export interface BacktestResults {
  generated_at: string;
  days: number;
  symbols: Record<string, BacktestSymbolResult>;
}

export interface TradingSignal {
  symbol: string;
  direction: 'BUY' | 'SELL' | 'NEUTRAL';
  score: number;
  quality: 'STRONG' | 'MODERATE' | 'WAIT';
  entry_price: number;
  sl: number;
  tp: number;
  recommended_lot: number;
  rr_ratio: number;
  atr: number;
  spread_points: number;
  reasons: string[];
  bot_approved?: boolean;
  broker_symbol?: string;
  data_source?: 'MT5' | 'OFFLINE';
  lot_exceeds_risk?: boolean;
  // Plan de entrada (zona + gatillo M5 + SL/TP por estructura)
  state?: SignalState;
  state_reason?: string;
  trigger?: string | null;
  expires_in?: number;
  executable?: boolean;
  entry_type?: 'ZONA' | 'MERCADO';
  zone_low?: number;
  zone_high?: number;
  tp1?: number;
  tp1_label?: string;
  tp2_label?: string;
  rr_tp1?: number;
  rr_tp2?: number;
  levels?: { name: string; price: number }[];
  history?: SignalHistory | null;
  auto_eligible?: boolean;
  pillars?: Pillars;
  environment?: Environment;
}

export interface AccountInfo {
  balance: number;
  equity: number;
  profit: number;
  margin?: number;
  free_margin?: number;
}

export interface RiskStatus {
  locked: boolean;
  starting_balance: number;
  current_equity: number;
  current_balance: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  lock_reason: string;
  max_daily_loss_pct: number;
}

export interface Position {
  ticket: number;
  symbol: string;
  type: 'BUY' | 'SELL';
  volume: number;
  price_open: number;
  price_current: number;
  sl: number;
  tp: number;
  profit: number;
  is_breakeven: boolean;
}

export interface BotLog {
  time: string;
  message: string;
  level: 'INFO' | 'SYSTEM' | 'SIGNAL' | 'TRADE' | 'PROFIT' | 'CRITICAL' | 'EXECUTION';
}

export interface TradeHistoryItem {
  id: number;
  ticket: number;
  symbol: string;
  direction: string;
  volume: number;
  entry_price: number;
  sl: number;
  tp: number;
  score: number | null;
  status: string;
  profit: number;
  close_price: number | null;
  open_time: string | null;
  close_time: string | null;
  leg?: 'TP1' | 'TP2' | 'UNICA' | null;
  group_id?: number | null;
  r_multiple?: number | null;
  mae_r?: number | null;
  mfe_r?: number | null;
  slippage_px?: number | null;
}

export interface MarketUpdate {
  type: string;
  mt5_connected?: boolean;
  mt5_status?: string;
  account: AccountInfo;
  risk: RiskStatus;
  autotrading: boolean;
  bot_logs: BotLog[];
  bot_mode: 'SNIPER' | 'INSTITUTIONAL' | 'DYNAMIC';
  signals: TradingSignal[];
  positions: Position[];
}

export interface JournalStats {
  n: number;
  expectancy_r: number | null;
  win_rate: number | null;
  total_r: number;
  avg_mae_r: number | null;
  avg_mfe_r: number | null;
  avg_slippage_px: number | null;
  by_symbol: Record<string, { n: number; expectancy_r: number | null; backtest_avg_r: number | null }>;
}
