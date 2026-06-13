"""Schema round-trip and validation tests."""

from __future__ import annotations

from datetime import date

import pytest
from conftest import peco_rate_r, seasonal_tariff, tou_tariff
from ratebook import (
    EffectiveRange,
    Tariff,
    validate_tariff,
)


@pytest.mark.parametrize("builder", [peco_rate_r, tou_tariff, seasonal_tariff])
def test_tariff_json_round_trip(builder) -> None:
    tariff = builder()
    restored = Tariff.from_json(tariff.to_json())
    assert restored == tariff
    # And round-trip is stable (idempotent JSON).
    assert restored.to_json() == tariff.to_json()


def test_decimal_serialized_as_string() -> None:
    j = peco_rate_r().to_json()
    rate = j["energy"]["periods"][0]["tiers"][0]["rate"]
    assert rate == "0.20513"
    assert isinstance(rate, str)


def test_effective_range_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="precedes start"):
        EffectiveRange(start=date(2026, 1, 1), end=date(2025, 1, 1))


def test_validate_tariff_clean_on_good_tariff() -> None:
    errors = [i for i in validate_tariff(peco_rate_r()) if i.severity == "error"]
    assert errors == []


def test_validate_8760_coverage_full_year() -> None:
    from ratebook.validate import validate_8760_coverage

    assert validate_8760_coverage(peco_rate_r().schedule, 2025) == []
    # Leap year must also be fully covered.
    assert validate_8760_coverage(peco_rate_r().schedule, 2024) == []
