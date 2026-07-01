"""Holiday pricing: named-holiday date rules, day-type override, and schedule round-trip."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from ratebook import (
    BillingWindow,
    Holiday,
    HolidayObservance,
    HolidayPolicy,
    Schedule,
    Usage,
    cheapest_charge_window,
    estimate_bill,
    holiday_dates,
    hourly_marginal_prices,
)

from conftest import tou_schedule, tou_tariff

ALL_TWELVE = tuple(Holiday)


def holiday_tou_tariff(
    holidays: tuple[Holiday, ...] = ALL_TWELVE,
    policy: HolidayPolicy = HolidayPolicy.AS_WEEKEND,
    observance: HolidayObservance = HolidayObservance.SUNDAY_TO_MONDAY,
):
    t = tou_tariff()  # weekday 16-20 peak $0.30, else / weekends $0.10
    return replace(
        t,
        schedule=replace(
            t.schedule, holiday_policy=policy, holidays=holidays, holiday_observance=observance
        ),
    )


# --------------------------------------------------------------------------------------
# Date rules
# --------------------------------------------------------------------------------------
def test_fixed_date_holidays_2026():
    dates = holiday_dates(2026, ALL_TWELVE, HolidayObservance.ACTUAL_DAY)
    assert date(2026, 1, 1) in dates  # New Year's (Thu)
    assert date(2026, 6, 19) in dates  # Juneteenth (Fri)
    assert date(2026, 7, 4) in dates  # Independence Day (Sat)
    assert date(2026, 11, 11) in dates  # Veterans Day (Wed)
    assert date(2026, 12, 25) in dates  # Christmas (Fri)


def test_floating_holidays_2026():
    dates = holiday_dates(2026, ALL_TWELVE, HolidayObservance.ACTUAL_DAY)
    assert date(2026, 1, 19) in dates  # MLK: 3rd Monday of January
    assert date(2026, 2, 16) in dates  # Washington's Birthday: 3rd Monday of February
    assert date(2026, 5, 25) in dates  # Memorial Day: last Monday of May
    assert date(2026, 9, 7) in dates  # Labor Day: 1st Monday of September
    assert date(2026, 10, 12) in dates  # Columbus Day: 2nd Monday of October
    assert date(2026, 11, 26) in dates  # Thanksgiving: 4th Thursday of November
    assert date(2026, 11, 27) in dates  # Day after Thanksgiving


def test_memorial_day_across_years():
    assert date(2025, 5, 26) in holiday_dates(2025, (Holiday.MEMORIAL_DAY,))
    assert date(2026, 5, 25) in holiday_dates(2026, (Holiday.MEMORIAL_DAY,))
    assert date(2027, 5, 31) in holiday_dates(2027, (Holiday.MEMORIAL_DAY,))


def test_sunday_to_monday_observance():
    # July 4, 2027 falls on a Sunday -> the following Monday is also a holiday.
    shifted = holiday_dates(2027, (Holiday.INDEPENDENCE_DAY,), HolidayObservance.SUNDAY_TO_MONDAY)
    assert date(2027, 7, 4) in shifted
    assert date(2027, 7, 5) in shifted
    actual = holiday_dates(2027, (Holiday.INDEPENDENCE_DAY,), HolidayObservance.ACTUAL_DAY)
    assert date(2027, 7, 5) not in actual
    # Saturday holidays never shift (July 4, 2026).
    sat = holiday_dates(2026, (Holiday.INDEPENDENCE_DAY,), HolidayObservance.SUNDAY_TO_MONDAY)
    assert sat == frozenset({date(2026, 7, 4)})


def test_only_requested_holidays_computed():
    dates = holiday_dates(2026, (Holiday.CHRISTMAS,))
    assert dates == frozenset({date(2026, 12, 25)})


# --------------------------------------------------------------------------------------
# Pricing behavior
# --------------------------------------------------------------------------------------
def test_as_weekend_prices_holiday_offpeak():
    t = holiday_tou_tariff()
    # Labor Day 2026 (Mon Sep 7): a weekday, but priced on the weekend schedule.
    prices = hourly_marginal_prices(t, BillingWindow(date(2026, 9, 7), 1))
    assert set(prices) == {Decimal("0.10")}
    # The next day is an ordinary Tuesday: 4-9pm peak applies.
    tuesday = hourly_marginal_prices(t, BillingWindow(date(2026, 9, 8), 1))
    assert tuesday[17] == Decimal("0.30")


def test_unknown_and_as_weekday_policies_unchanged():
    for policy in (HolidayPolicy.UNKNOWN, HolidayPolicy.AS_WEEKDAY):
        t = holiday_tou_tariff(policy=policy)
        prices = hourly_marginal_prices(t, BillingWindow(date(2026, 9, 7), 1))
        assert prices[17] == Decimal("0.30"), policy


def test_as_weekend_without_enumerated_holidays_is_inert_and_warned():
    t = holiday_tou_tariff(holidays=())
    prices = hourly_marginal_prices(t, BillingWindow(date(2026, 9, 7), 1))
    assert prices[17] == Decimal("0.30")
    bill = estimate_bill(t, Usage.hourly([1] * 24), BillingWindow(date(2026, 9, 7), 1))
    assert "holidays_not_enumerated" in bill.warnings


def test_enumerated_holidays_drop_the_warning():
    t = holiday_tou_tariff()
    bill = estimate_bill(t, Usage.aggregate(100), BillingWindow(date(2026, 9, 7), 1))
    assert "holidays_not_enumerated" not in bill.warnings


def test_holiday_affects_bill_period_accumulation():
    t = holiday_tou_tariff()
    plain = holiday_tou_tariff(policy=HolidayPolicy.UNKNOWN)
    window = BillingWindow(date(2026, 9, 7), 1)  # Labor Day only
    load = Usage.hourly([1] * 24)
    holiday_bill = estimate_bill(t, load, window)
    plain_bill = estimate_bill(plain, load, window)
    # 24 kWh all off-peak vs 5 peak hours at $0.30.
    assert holiday_bill.total == Decimal("2.40")
    assert plain_bill.total == Decimal("3.40")


def test_cheapest_charge_window_sees_holiday():
    t = holiday_tou_tariff()
    # Window = Sun Sep 6 + Labor Day Mon Sep 7. Every hour is off-peak, so the earliest
    # block wins; without holiday support the Monday peak would push the average up.
    cw = cheapest_charge_window(t, BillingWindow(date(2026, 9, 6), 2), 4)
    assert cw.avg_rate == Decimal("0.10")
    plain = tou_tariff()
    cw_plain = cheapest_charge_window(
        plain, BillingWindow(date(2026, 9, 6), 2), 24, not_before=None
    )
    assert cw_plain.avg_rate > Decimal("0.10") or cw_plain.start.date() == date(2026, 9, 6)


# --------------------------------------------------------------------------------------
# Schema round-trip
# --------------------------------------------------------------------------------------
def test_schedule_json_round_trip_with_holidays():
    s = tou_schedule()
    s = replace(
        s,
        holiday_policy=HolidayPolicy.AS_WEEKEND,
        holidays=(Holiday.NEW_YEARS_DAY, Holiday.CHRISTMAS),
        holiday_observance=HolidayObservance.ACTUAL_DAY,
    )
    d = s.to_json()
    assert d["holidays"] == ["new_years_day", "christmas"]
    assert d["holiday_observance"] == "actual_day"
    assert Schedule.from_json(d) == s


def test_schedule_json_omits_defaults():
    d = tou_schedule().to_json()
    assert "holidays" not in d
    assert "holiday_observance" not in d
    assert Schedule.from_json(d) == tou_schedule()


def test_duplicate_holidays_rejected():
    with pytest.raises(ValueError, match="unique"):
        replace(tou_schedule(), holidays=(Holiday.CHRISTMAS, Holiday.CHRISTMAS))
