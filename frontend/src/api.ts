export const DEFAULT_API_BASE = 'http://127.0.0.1:8765';
export const LOCAL_PANEL_URL = 'http://localhost:5180';
export const SERVICE_ID = 'mt5-senales';
const STORAGE_KEY = 'mt5quant.apiBase';

export function getApiBase(): string {
  const fromEnv = (import.meta.env.VITE_API_BASE as string | undefined)?.trim() ?? '';
  let stored = '';
  try {
    stored = localStorage.getItem(STORAGE_KEY)?.trim() ?? '';
  } catch {
    stored = '';
  }
  return (stored || fromEnv || DEFAULT_API_BASE).replace(/\/$/, '');
}

export function setApiBase(url: string) {
  const clean = url.trim().replace(/\/$/, '');
  try {
    if (!clean || clean === DEFAULT_API_BASE) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, clean);
  } catch {
    /* el panel sigue con el valor por defecto */
  }
}

export function apiUrl(path: string): string {
  return `${getApiBase()}${path.startsWith('/') ? path : `/${path}`}`;
}

export function wsUrl(path: string): string {
  const http = apiUrl(path);
  if (http.startsWith('https://')) return `wss://${http.slice('https://'.length)}`;
  if (http.startsWith('http://')) return `ws://${http.slice('http://'.length)}`;
  return http;
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(apiUrl(path), init);
}

export type EngineState = 'checking' | 'ok' | 'offline' | 'foreign';

export interface EngineStatus {
  state: EngineState;
  canTrade: boolean;
  version?: string;
  localPanel: string;
}

export async function checkEngine(): Promise<EngineStatus> {
  const base: EngineStatus = { state: 'offline', canTrade: false, localPanel: LOCAL_PANEL_URL };
  let res: Response;
  try {
    res = await apiFetch('/status', { cache: 'no-store' });
  } catch {
    return base;
  }
  try {
    const body = await res.json();
    if (!res.ok || body?.service !== SERVICE_ID) return { ...base, state: 'foreign' };
    return {
      state: 'ok',
      canTrade: Boolean(body.can_trade),
      version: body.version,
      localPanel: body.local_panel || LOCAL_PANEL_URL,
    };
  } catch {
    return { ...base, state: 'foreign' };
  }
}
