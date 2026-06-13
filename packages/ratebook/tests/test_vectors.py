"""Golden cross-engine bill vectors.

``tests/vectors/v0_bills.json`` is the language-agnostic oracle: the future TypeScript port
runs the identical file and must reproduce ``expected`` byte-for-byte (Decimal-as-string
makes that achievable). Here, the vectors double as regression guards — any engine change
that alters output breaks this test, forcing an intentional regeneration.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from ratebook import BillingWindow, Tariff, Usage, estimate_bill

VECTORS = Path(__file__).parent / "vectors" / "v0_bills.json"


def _load_cases():
    data = json.loads(VECTORS.read_text())
    return data["cases"]


def _usage_from_json(u: dict) -> Usage:
    if "hourly_kwh" in u:
        return Usage.hourly(u["hourly_kwh"])
    return Usage.aggregate(u["total_kwh"])


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_vector_reproduces_expected(case: dict) -> None:
    tariff = Tariff.from_json(case["tariff"])
    usage = _usage_from_json(case["usage"])
    window = BillingWindow(date.fromisoformat(case["window"]["start"]), case["window"]["days"])
    result = estimate_bill(tariff, usage, window)
    assert result.to_json() == case["expected"]


def test_vectors_present() -> None:
    assert len(_load_cases()) >= 4
