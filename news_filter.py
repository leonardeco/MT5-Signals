import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
import MetaTrader5 as mt5

COLOMBIA_TZ = timezone(timedelta(hours=-5))
CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_REFRESH_SECONDS = 4 * 3600   # el feed limita peticiones frecuentes
CALENDAR_RETRY_SECONDS = 300          # tras un fallo, no reintentar en cada ciclo del escáner (bloquea 5 s)
CALENDAR_MAX_AGE_SECONDS = 12 * 3600  # sin datos más recientes que esto, se bloquea por seguridad


def download_calendar() -> list[dict]:
    req = urllib.request.Request(CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Formato de calendario inesperado")
    return [e for e in data if e.get("impact") == "High"]


INDEX_HINTS = ("US100", "USTEC", "NAS100", "NDX", "NQ100")
CURRENCIES = ("XAU", "XAG", "EUR", "GBP", "JPY", "USD", "AUD", "CAD", "CHF", "NZD")


def exposure_legs(symbol: str) -> set[str]:
    """Riesgos que mueve un símbolo: las dos divisas de un par, el oro, o el índice (US100 cuenta como índice)."""
    sym = symbol.upper()
    if any(h in sym for h in INDEX_HINTS):
        return {"US100"}
    return {c for c in CURRENCIES if c in sym} or {sym}


def exposure_check(symbol: str, open_symbols: list[str], max_per_leg: int) -> tuple[bool, str]:
    """Bloquea si alguna pata del símbolo ya está en max_per_leg símbolos con posición abierta (cualquier origen).
    Se cuentan símbolos distintos: las dos patas TP1/TP2 de una orden dividida son una sola exposición."""
    counts: dict[str, int] = {}
    for s in set(open_symbols):
        for leg in exposure_legs(s):
            counts[leg] = counts.get(leg, 0) + 1
    full = sorted(leg for leg in exposure_legs(symbol) if counts.get(leg, 0) >= max_per_leg)
    if full:
        return False, f"Exposición máxima en {', '.join(full)} ({max_per_leg} símbolos abiertos)"
    return True, "Exposición libre"


class MarketEnvironmentFilter:
    def __init__(self, session_start=2, session_end=15, news_window=15, max_usd_trades=2,
                 fetch=download_calendar, clock=time.time, cache_path: str | None = None):
        self.session_start_hour = session_start
        self.session_end_hour = session_end
        self.news_window_minutes = news_window
        self.max_usd_correlated_trades = max_usd_trades
        self._fetch = fetch
        self._clock = clock
        self._cache_path = cache_path
        self._cached_events = []
        self._last_success_ts = 0.0
        self._last_attempt_ts = 0.0
        self._load_disk_cache()

    def _load_disk_cache(self):
        """El feed responde 429 si se pide en cada arranque: la última descarga buena sobrevive a reinicios."""
        if not self._cache_path or not os.path.isfile(self._cache_path):
            return
        try:
            with open(self._cache_path, encoding="utf-8") as handle:
                saved = json.load(handle)
            fetched_at = float(saved["fetched_at"])
            events = saved["events"]
            if isinstance(events, list) and fetched_at <= self._clock():
                self._cached_events = events
                self._last_success_ts = fetched_at
        except Exception as e:
            print(f"[News] Caché del calendario ilegible, se ignora: {e}")

    def _save_disk_cache(self):
        if not self._cache_path:
            return
        tmp = f"{self._cache_path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"fetched_at": self._last_success_ts, "events": self._cached_events}, handle)
            os.replace(tmp, self._cache_path)
        except OSError as e:
            print(f"[News] No se pudo guardar la caché del calendario: {e}")

    def _refresh_calendar(self):
        now = self._clock()
        if self._last_success_ts and now - self._last_success_ts < CALENDAR_REFRESH_SECONDS:
            return
        if self._last_attempt_ts and now - self._last_attempt_ts < CALENDAR_RETRY_SECONDS:
            return
        self._last_attempt_ts = now
        try:
            self._cached_events = self._fetch()
            self._last_success_ts = now
            self._save_disk_cache()
        except Exception as e:
            print(f"[News] No se pudo actualizar el calendario: {e}")

    def calendar_status(self) -> tuple[bool, str]:
        """(vigente, mensaje). Sin calendario reciente no se sabe si hay noticia: se trata como bloqueo."""
        if not self._last_success_ts:
            return False, "Calendario de noticias no disponible: auto-trading bloqueado por seguridad"
        age = self._clock() - self._last_success_ts
        if age > CALENDAR_MAX_AGE_SECONDS:
            return False, f"Calendario de noticias sin actualizar hace {age / 3600:.0f} h: auto-trading bloqueado por seguridad"
        return True, ""

    @staticmethod
    def _extract_currencies(symbol: str) -> set:
        sym = symbol.upper()
        curr = {"USD"}
        for c in ("EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"):
            if c in sym:
                curr.add(c)
        return curr

    def evaluate_environment(self, symbol: str) -> dict:
        now_col = datetime.now(COLOMBIA_TZ)
        now_utc = datetime.now(timezone.utc)
        self._refresh_calendar()
        
        session_ok = self.session_start_hour <= now_col.hour < self.session_end_hour and now_col.weekday() < 5
        session_msg = "Dentro de sesión operativa" if session_ok else "Fuera de horario operativo"
        
        calendar_ok, calendar_msg = self.calendar_status()
        news_blocked = not calendar_ok
        news_msg = calendar_msg or "Sin noticias de alto impacto cercanas"
        relevant_currencies = self._extract_currencies(symbol)

        for ev in (self._cached_events if calendar_ok else []):
            if ev.get("country", "").upper() in relevant_currencies and ev.get("date"):
                try:
                    ev_time = datetime.fromisoformat(ev["date"]).astimezone(timezone.utc)
                    diff = (ev_time - now_utc).total_seconds() / 60.0
                    if abs(diff) <= self.news_window_minutes:
                        news_blocked = True
                        mins = int(round(diff))
                        news_msg = f"Noticia {ev['country']} ({ev.get('title', 'High Impact')}) en {mins} min"
                        break
                except Exception:
                    continue

        try:
            positions = mt5.positions_get() or []
        except Exception:
            positions = []

        corr_ok, corr_msg = exposure_check(symbol, [p.symbol for p in positions], self.max_usd_correlated_trades)

        return {
            "allowed": session_ok and not news_blocked and corr_ok,
            "session_ok": session_ok,
            "session_message": session_msg,
            "news_blocked": news_blocked,
            "news_message": news_msg,
            "calendar_ok": calendar_ok,
            "correlation_ok": corr_ok,
            "correlation_message": corr_msg,
        }
