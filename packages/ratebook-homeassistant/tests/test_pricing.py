"""Tests for the pure pricing adapter (no Home Assistant needed)."""

from __future__ import annotations

from datetime import date, datetime

from ratebook_ha import pricing

# 2025-06-02 is a Monday (weekday); the bundled generic-tou peak window is 16:00-21:00.
MONDAY = date(2025, 6, 2)


def test_bundled_tariffs_present() -> None:
    names = pricing.list_bundled()
    assert "generic-tou" in names
    assert "flat-residential" in names


def test_current_price_tracks_tou_periods() -> None:
    tou = pricing.load_bundled("generic-tou")
    assert pricing.current_price(tou, datetime(2025, 6, 2, 3)) == 0.12  # 3am off-peak
    assert pricing.current_price(tou, datetime(2025, 6, 2, 18)) == 0.30  # 6pm peak


def test_hourly_schedule_is_24_entries() -> None:
    sched = pricing.hourly_schedule(pricing.load_bundled("generic-tou"), MONDAY)
    assert len(sched) == 24
    assert sched[18]["price"] == 0.30
    assert sched[18]["start"] == "2025-06-02T18:00:00"


def test_cheapest_window_avoids_peak() -> None:
    win = pricing.cheapest_window(
        pricing.load_bundled("generic-tou"), MONDAY, days=1, charge_hours=4
    )
    assert win["avg_rate"] == 0.12  # an all-off-peak block exists
    assert win["hours"] == 4


def test_flat_tariff_constant_price() -> None:
    flat = pricing.load_bundled("flat-residential")
    assert pricing.current_price(flat, datetime(2025, 6, 2, 3)) == 0.16
    assert pricing.current_price(flat, datetime(2025, 6, 2, 18)) == 0.16


def test_load_tariff_from_json_string() -> None:
    import json

    text = json.dumps(pricing.load_bundled("flat-residential").to_json())
    tariff = pricing.load_tariff(text)
    assert pricing.current_price(tariff, datetime(2025, 6, 2, 12)) == 0.16
