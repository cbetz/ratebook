"""Tests for the pure pricing adapter (no Home Assistant needed)."""

from __future__ import annotations

from datetime import UTC, date, datetime

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


def test_evcc_forecast_shape_and_values() -> None:
    tou = pricing.load_bundled("generic-tou")
    start = datetime(2025, 6, 2, 0, tzinfo=UTC)  # Mon 00:00 UTC
    fc = pricing.evcc_forecast(tou, start, 24)
    assert len(fc) == 24
    assert set(fc[0]) == {"start", "end", "value"}
    assert fc[0]["start"] == "2025-06-02T00:00:00+00:00"
    assert fc[0]["end"] == "2025-06-02T01:00:00+00:00"
    assert fc[3]["value"] == 0.12  # 3am off-peak
    assert fc[18]["value"] == 0.30  # 6pm peak


def test_emhass_cost_forecast_current_first() -> None:
    tou = pricing.load_bundled("generic-tou")
    # Start at 18:00 (peak): first value is peak, later off-peak hours appear in order.
    prices = pricing.emhass_cost_forecast(tou, datetime(2025, 6, 2, 18, tzinfo=UTC), 6)
    assert len(prices) == 6
    assert prices[0] == 0.30  # 18:00 peak (current period first)
    assert prices[3] == 0.12  # 21:00 back to off-peak


def test_bundled_index_has_labels_for_every_tariff() -> None:
    index = pricing.bundled_index()
    assert {e["slug"] for e in index} == set(pricing.list_bundled())
    labels = {e["slug"]: e["label"] for e in index}
    # Real utilities carry human dropdown labels, not raw slugs.
    assert labels["pge-e-1"].startswith("PG&E")
    assert "(CA)" in labels["pge-e-1"]
    # Sorted by label.
    assert [e["label"] for e in index] == sorted((e["label"] for e in index), key=str.lower)


def test_index_json_is_not_listed_as_a_tariff() -> None:
    assert "index" not in pricing.list_bundled()


def test_tier_changes_marginal_price_on_tiered_plans() -> None:
    pge = pricing.load_bundled("pge-e-1")
    noon = datetime(2025, 6, 2, 12)
    assert pricing.current_price(pge, noon, tier=0) == 0.32561
    assert pricing.current_price(pge, noon, tier=1) == 0.40702
    # Tier index clamps to the ladder length rather than raising.
    assert pricing.current_price(pge, noon, tier=9) == 0.40702
    # Schedules and windows honor the tier too.
    assert pricing.hourly_schedule(pge, MONDAY, tier=1)[0]["price"] == 0.40702
    win = pricing.cheapest_window(pge, MONDAY, days=1, charge_hours=4, tier=1)
    assert win["avg_rate"] == 0.40702


def test_nordpool_schedule_shape() -> None:
    tou = pricing.load_bundled("generic-tou")
    raw = pricing.nordpool_schedule(tou, MONDAY)
    assert len(raw) == 24
    assert raw[18] == {
        "start": "2025-06-02T18:00:00",
        "end": "2025-06-02T19:00:00",
        "value": 0.30,
    }


def test_is_holiday_requires_policy_and_dates() -> None:
    # The generic example tariff carries no holiday rule (holiday_policy unknown), so it is
    # never holiday-typed; audited TOU plans (e.g. peco-rate-r-tou) enumerate theirs.
    tou = pricing.load_bundled("generic-tou")
    assert pricing.is_holiday(tou, date(2025, 9, 1)) is False  # Labor Day 2025
    holiday_json = tou.to_json()
    holiday_json["schedule"]["holiday_policy"] = "as_weekend"
    holiday_json["schedule"]["holidays"] = ["labor_day"]
    t = pricing.load_tariff(holiday_json)
    assert pricing.is_holiday(t, date(2025, 9, 1)) is True
    assert pricing.is_holiday(t, date(2025, 9, 2)) is False
    # And the price on the holiday follows the weekend schedule (all off-peak).
    assert pricing.current_price(t, datetime(2025, 9, 1, 18)) == 0.12
