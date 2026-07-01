"""Regenerate the cross-engine holiday vectors.

Run: ``uv run python packages/ratebook/tests/generate_holiday_vectors.py``

Writes ``tests/vectors/v0_holidays.json`` — the language-agnostic oracle for holiday-aware
day-typing that BOTH the Python engine (``test_holiday_vectors.py``) and the TypeScript port
(``holiday_vectors.test.ts``) must reproduce byte-for-byte: hourly marginal prices, bills,
and charge windows over windows that contain named US holidays.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conftest import tou_tariff
from ratebook import (
    BillingWindow,
    Holiday,
    HolidayObservance,
    HolidayPolicy,
    Usage,
    cheapest_charge_window,
    estimate_bill,
    hourly_marginal_prices,
)
from ratebook.money import decimal_to_json

ALL_TWELVE = tuple(Holiday)


def holiday_tou(
    holidays=ALL_TWELVE,
    policy=HolidayPolicy.AS_WEEKEND,
    observance=HolidayObservance.SUNDAY_TO_MONDAY,
):
    t = tou_tariff()  # weekday 16-20 peak $0.30, else / weekends $0.10
    return replace(
        t,
        schedule=replace(
            t.schedule, holiday_policy=policy, holidays=holidays, holiday_observance=observance
        ),
    )


def _price_case(name, tariff, start, days, tier=0):
    prices = hourly_marginal_prices(tariff, BillingWindow(start, days), tier=tier)
    return {
        "name": name,
        "tariff": tariff.to_json(),
        "window": {"start": start.isoformat(), "days": days},
        "tier": tier,
        "expected": [decimal_to_json(p) for p in prices],
    }


def _bill_case(name, tariff, usage_json, start, days):
    usage = (
        Usage.hourly(usage_json["hourly_kwh"])
        if "hourly_kwh" in usage_json
        else Usage.aggregate(usage_json["total_kwh"])
    )
    result = estimate_bill(tariff, usage, BillingWindow(start, days))
    return {
        "name": name,
        "tariff": tariff.to_json(),
        "usage": usage_json,
        "window": {"start": start.isoformat(), "days": days},
        "expected": result.to_json(),
    }


def _charge_case(name, tariff, start, days, charge_hours):
    cw = cheapest_charge_window(tariff, BillingWindow(start, days), charge_hours)
    return {
        "name": name,
        "tariff": tariff.to_json(),
        "window": {"start": start.isoformat(), "days": days},
        "charge_hours": charge_hours,
        "expected": cw.to_json(),
    }


def build() -> dict:
    flat_day = ["1"] * 24
    return {
        "price_cases": [
            _price_case(
                "Labor Day 2026 (Mon) prices as weekend under as_weekend",
                holiday_tou(),
                date(2026, 9, 7),
                1,
            ),
            _price_case(
                "same Monday stays peak under unknown policy",
                holiday_tou(policy=HolidayPolicy.UNKNOWN),
                date(2026, 9, 7),
                1,
            ),
            _price_case(
                "July 5 2027 (Mon after Sunday July 4) shifts under sunday_to_monday",
                holiday_tou(holidays=(Holiday.INDEPENDENCE_DAY,)),
                date(2027, 7, 5),
                1,
            ),
            _price_case(
                "July 5 2027 stays peak under actual_day observance",
                holiday_tou(
                    holidays=(Holiday.INDEPENDENCE_DAY,),
                    observance=HolidayObservance.ACTUAL_DAY,
                ),
                date(2027, 7, 5),
                1,
            ),
        ],
        "bill_cases": [
            _bill_case(
                "Labor Day 2026: 24x1 kWh bills all off-peak",
                holiday_tou(),
                {"hourly_kwh": flat_day},
                date(2026, 9, 7),
                1,
            ),
            _bill_case(
                "as_weekend with empty holidays: inert + holidays_not_enumerated warning",
                holiday_tou(holidays=()),
                {"hourly_kwh": flat_day},
                date(2026, 9, 7),
                1,
            ),
        ],
        "charge_cases": [
            _charge_case(
                "Thanksgiving week 2026: 4h window across Thu+Fri holidays",
                holiday_tou(),
                date(2026, 11, 25),
                3,
                4,
            ),
        ],
    }


if __name__ == "__main__":
    out = Path(__file__).parent / "vectors" / "v0_holidays.json"
    out.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {out}")
