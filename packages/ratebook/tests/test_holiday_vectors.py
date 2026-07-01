"""Cross-engine holiday vectors: the engine must reproduce v0_holidays.json.

Both the Python engine and the TypeScript port (holiday_vectors.test.ts) read the SAME file;
regenerate it with `uv run python packages/ratebook/tests/generate_holiday_vectors.py`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from ratebook import (
    BillingWindow,
    Tariff,
    Usage,
    cheapest_charge_window,
    estimate_bill,
    hourly_marginal_prices,
)
from ratebook.money import decimal_to_json

VECTORS = json.loads((Path(__file__).parent / "vectors" / "v0_holidays.json").read_text())


def _window(case: dict) -> BillingWindow:
    return BillingWindow(date.fromisoformat(case["window"]["start"]), case["window"]["days"])


@pytest.mark.parametrize(
    "case", VECTORS["price_cases"], ids=[c["name"] for c in VECTORS["price_cases"]]
)
def test_holiday_price_vector(case: dict) -> None:
    prices = hourly_marginal_prices(
        Tariff.from_json(case["tariff"]), _window(case), tier=case["tier"]
    )
    assert [decimal_to_json(p) for p in prices] == case["expected"]


@pytest.mark.parametrize(
    "case", VECTORS["bill_cases"], ids=[c["name"] for c in VECTORS["bill_cases"]]
)
def test_holiday_bill_vector(case: dict) -> None:
    usage = (
        Usage.hourly(case["usage"]["hourly_kwh"])
        if "hourly_kwh" in case["usage"]
        else Usage.aggregate(case["usage"]["total_kwh"])
    )
    result = estimate_bill(Tariff.from_json(case["tariff"]), usage, _window(case))
    assert result.to_json() == case["expected"]


@pytest.mark.parametrize(
    "case", VECTORS["charge_cases"], ids=[c["name"] for c in VECTORS["charge_cases"]]
)
def test_holiday_charge_vector(case: dict) -> None:
    cw = cheapest_charge_window(
        Tariff.from_json(case["tariff"]), _window(case), case["charge_hours"]
    )
    assert cw.to_json() == case["expected"]
