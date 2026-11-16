export const DEFAULT_API_BASE = 'http://127.0.0.1:8765';
export const LOCAL_PANEL_URL = 'http://localhost:5180';
export const SERVICE_ID = 'mt5-senales';
const STORAGE_KEY = 'mt5quant.apiBase';
const TOKEN_KEY = 'mt5quant.token';

// Clave del motor (solo cuando el motor está en un VPS). Se guarda únicamente en este navegador.
export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY)?.trim() ?? '';
  } catch {
    return '';
  }
}

export function setToken(token: string) {
  try {
    if (token.trim()) localStorage.setItem(TOKEN_KEY, token.trim());
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* sin almacenamiento el panel funciona sin clave */
  }
}

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
  const token = getToken();
  if (!token) return fetch(apiUrl(path), init);
  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);
  return fetch(apiUrl(path), { ...init, headers });
}

// El navegador no deja poner cabeceras en un WebSocket: la clave va como subprotocolo, nunca en la URL
export function openSocket(path: string): WebSocket {
  const token = getToken();
  return token ? new WebSocket(wsUrl(path), ['bearer', token]) : new WebSocket(wsUrl(path));
}

export type EngineState = 'checking' | 'ok' | 'offline' | 'foreign' | 'locked';

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
    if (body.auth_required && !body.authenticated) return { ...base, state: 'locked', version: body.version };
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
