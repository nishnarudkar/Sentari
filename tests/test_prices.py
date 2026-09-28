import datetime as dt

import pytest

from evaluation.prices import day0_index, event_returns

DAYS = [dt.date(2024, 1, d) for d in (2, 3, 4, 5, 8, 9, 10, 11, 12, 16, 17, 18, 19, 22, 23)]


def test_day0_depends_on_call_time():
    assert DAYS[day0_index(DAYS, dt.datetime(2024, 1, 4, 8, 30))] == dt.date(2024, 1, 4)   # before the open
    assert DAYS[day0_index(DAYS, dt.datetime(2024, 1, 4, 17, 0))] == dt.date(2024, 1, 5)   # after the close
    assert DAYS[day0_index(DAYS, dt.datetime(2024, 1, 5, 17, 0))] == dt.date(2024, 1, 8)   # over a weekend


def test_event_returns_are_market_adjusted():
    stock = {d: 100.0 for d in DAYS}
    market = {d: 100.0 for d in DAYS}
    for d in DAYS[3:]:
        stock[d] = 110.0   # +10% from day 0 (Jan 5) onwards
    for d in DAYS[3:]:
        market[d] = 102.0  # market +2%
    r = event_returns(stock, market, dt.datetime(2024, 1, 4, 17, 0))
    assert r["day0"] == "2024-01-05"
    assert r["car_0_1"] == pytest.approx(0.08) and r["car_0_4"] == pytest.approx(0.08)
    assert r["drift_2_11"] == pytest.approx(0.0)


def test_event_without_enough_future_days_is_skipped():
    stock = market = {d: 100.0 for d in DAYS}
    assert event_returns(stock, market, dt.datetime(2024, 1, 22, 9, 0)) is None
