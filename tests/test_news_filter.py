import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import news_filter  # noqa: E402
from news_filter import MarketEnvironmentFilter  # noqa: E402


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def failing_fetch(calls):
    def fetch():
        calls.append(1)
        raise OSError("sin red")
    return fetch


def event_in(minutes, country="USD"):
    when = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return {"country": country, "title": "NFP", "impact": "High", "date": when.isoformat()}


def test_calendar_never_downloaded_blocks_trading():
    calls = []
    env = MarketEnvironmentFilter(fetch=failing_fetch(calls), clock=Clock()).evaluate_environment("EURUSD")
    assert env["news_blocked"] and not env["allowed"] and not env["calendar_ok"]
    assert "no disponible" in env["news_message"]


def test_failed_download_is_not_retried_every_cycle():
    calls, clock = [], Clock()
    f = MarketEnvironmentFilter(fetch=failing_fetch(calls), clock=clock)
    for _ in range(5):
        f.evaluate_environment("EURUSD")
    assert len(calls) == 1
    clock.t += news_filter.CALENDAR_RETRY_SECONDS + 1
    f.evaluate_environment("EURUSD")
    assert len(calls) == 2


def test_fresh_calendar_without_nearby_events_does_not_block_news():
    f = MarketEnvironmentFilter(fetch=lambda: [event_in(180)], clock=Clock())
    env = f.evaluate_environment("EURUSD")
    assert env["calendar_ok"] and not env["news_blocked"]


def test_nearby_high_impact_event_blocks():
    f = MarketEnvironmentFilter(fetch=lambda: [event_in(5)], clock=Clock())
    env = f.evaluate_environment("XAUUSD")
    assert env["news_blocked"] and "NFP" in env["news_message"]


def test_event_of_unrelated_currency_does_not_block():
    f = MarketEnvironmentFilter(fetch=lambda: [event_in(5, "AUD")], clock=Clock())
    assert not f.evaluate_environment("EURUSD")["news_blocked"]


def test_stale_calendar_blocks_after_max_age():
    clock, calls = Clock(), []
    ok = [True]

    def fetch():
        calls.append(1)
        if ok[0]:
            return []
        raise OSError("caído")

    f = MarketEnvironmentFilter(fetch=fetch, clock=clock)
    assert f.evaluate_environment("EURUSD")["calendar_ok"]
    ok[0] = False
    clock.t += news_filter.CALENDAR_MAX_AGE_SECONDS - 60      # aún vale la copia en caché
    assert f.evaluate_environment("EURUSD")["calendar_ok"]
    clock.t += 120
    env = f.evaluate_environment("EURUSD")
    assert not env["calendar_ok"] and env["news_blocked"] and "sin actualizar" in env["news_message"]


# ---------- Exposición por divisa ----------

from news_filter import exposure_check, exposure_legs  # noqa: E402


def test_exposure_legs():
    assert exposure_legs("EURUSD") == {"EUR", "USD"}
    assert exposure_legs("XAUUSD") == {"XAU", "USD"}
    assert exposure_legs("USTEC") == exposure_legs("US100") == {"US100"}
    assert exposure_legs("USDJPY.m") == {"USD", "JPY"}


def test_exposure_blocks_only_the_saturated_currency():
    ok, msg = exposure_check("GBPUSD", ["EURUSD", "XAUUSD"], 2)
    assert not ok and "USD" in msg
    assert exposure_check("US100", ["EURUSD", "XAUUSD"], 2)[0]      # el índice no comparte patas
    assert exposure_check("EURUSD", ["USTEC", "USTEC"], 2)[0]
    assert exposure_check("EURUSD", [], 2) == (True, "Exposición libre")
    assert exposure_check("GBPUSD", ["EURUSD", "EURUSD"], 2)[0]  # dos patas de la misma orden dividida
