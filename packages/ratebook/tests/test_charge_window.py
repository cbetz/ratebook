"""Tests for the charge-window optimization (the 'when should I charge?' engine math)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from conftest import peco_rate_r, tou_tariff
from ratebook import BillingWindow, cheapest_charge_window, hourly_marginal_prices

# tou_tariff: weekday hours 16-20 are peak (period 1 @ $0.30), everything else off-peak @ $0.10.
MONDAY = BillingWindow(date(2025, 6, 2), 1)  # 2025-06-02 is a Monday


def test_marginal_prices_reflect_tou_schedule() -> None:
    prices = hourly_marginal_prices(tou_tariff(), MONDAY)
    assert len(prices) == 24
    assert prices[17] == Decimal("0.30")  # 5pm is peak
    assert prices[3] == Decimal("0.10")  # 3am is off-peak


def test_cheapest_window_avoids_peak() -> None:
    cw = cheapest_charge_window(tou_tariff(), MONDAY, 4)
    assert cw.avg_rate == Decimal("0.10")  # an all-off-peak block exists
    assert all(r == Decimal("0.10") for r in cw.hourly_rates)


def test_long_window_must_include_peak_costs_more() -> None:
    # A 22-hour block can't avoid the 5 peak hours, so its average exceeds the off-peak rate.
    cw = cheapest_charge_window(tou_tariff(), MONDAY, 22)
    assert cw.avg_rate > Decimal("0.10")


def test_flat_tariff_picks_earliest_window() -> None:
    cw = cheapest_charge_window(peco_rate_r(), MONDAY, 3)
    assert cw.start == datetime(2025, 6, 2, 0, 0)
    assert cw.avg_rate == Decimal("0.21884")


def test_charge_hours_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="out of range"):
        cheapest_charge_window(peco_rate_r(), MONDAY, 25)


def test_not_before_excludes_past_windows() -> None:
    # Flat tariff: every block ties, so with no cutoff it picks 00:00 (the earliest). With a
    # mid-morning cutoff the window must start at the next whole hour — never in the past.
    cw = cheapest_charge_window(peco_rate_r(), MONDAY, 3, not_before=datetime(2025, 6, 2, 10, 30))
    assert cw.start == datetime(2025, 6, 2, 11, 0)


def test_not_before_before_window_start_is_noop() -> None:
    cw = cheapest_charge_window(peco_rate_r(), MONDAY, 3, not_before=datetime(2025, 6, 1, 0, 0))
    assert cw.start == datetime(2025, 6, 2, 0, 0)  # earliest — same as no cutoff


def test_not_before_past_last_block_clamps_to_latest() -> None:
    # 24h window, 3h block → latest start is 21:00; a cutoff beyond that returns the last block.
    cw = cheapest_charge_window(peco_rate_r(), MONDAY, 3, not_before=datetime(2025, 6, 2, 23, 30))
    assert cw.start == datetime(2025, 6, 2, 21, 0)


def test_not_before_with_tou_picks_upcoming_offpeak() -> None:
    # From noon, the cheapest upcoming 4h block is all off-peak (before the 4-8pm peak).
    cw = cheapest_charge_window(tou_tariff(), MONDAY, 4, not_before=datetime(2025, 6, 2, 12, 0))
    assert cw.start >= datetime(2025, 6, 2, 12, 0)
    assert cw.avg_rate == Decimal("0.10")
