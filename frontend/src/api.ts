const DEFAULT_API_BASE = 'http://127.0.0.1:8000';
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
