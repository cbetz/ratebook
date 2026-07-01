"""Property-based invariants (hypothesis). These are the guardrails a correctness-critical
engine must never violate, regardless of inputs."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from ratebook import (
    BillingWindow,
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    Tariff,
    Usage,
    estimate_bill,
)

from conftest import flat_schedule, peco_rate_r, tiered_tariff, tou_tariff

JUNE = BillingWindow(date(2025, 6, 1), 30)

kwh = st.decimals(min_value=0, max_value=100000, places=2, allow_nan=False, allow_infinity=False)


@given(usage=kwh)
def test_flat_rate_closed_form(usage: Decimal) -> None:
    result = estimate_bill(peco_rate_r(), Usage(total_kwh=usage), JUNE)
    assert result.ok
    assert result.total == usage * Decimal("0.21884") + Decimal("11.30")


@given(a=kwh, b=kwh)
def test_monotonic_in_usage(a: Decimal, b: Decimal) -> None:
    lo, hi = sorted((a, b))
    bill_lo = estimate_bill(tiered_tariff(), Usage(total_kwh=lo), JUNE)
    bill_hi = estimate_bill(tiered_tariff(), Usage(total_kwh=hi), JUNE)
    assert bill_hi.total >= bill_lo.total


@given(usage=kwh)
def test_energy_charge_equals_line_item_sum(usage: Decimal) -> None:
    result = estimate_bill(tiered_tariff(), Usage(total_kwh=usage), JUNE)
    energy_items = [li for li in result.line_items if li.period >= 0]
    assert sum((li.subtotal for li in energy_items), Decimal(0)) == result.energy_charge


@given(usage=kwh)
def test_tier_partition_covers_all_kwh(usage: Decimal) -> None:
    # Every kWh is billed in exactly one tier slice: the slices sum to the input.
    result = estimate_bill(tiered_tariff(), Usage(total_kwh=usage), JUNE)
    energy_items = [li for li in result.line_items if li.period >= 0]
    assert sum((li.kwh for li in energy_items), Decimal(0)) == usage


@given(
    load=st.lists(
        st.decimals(min_value=0, max_value=50, places=1, allow_nan=False, allow_infinity=False),
        min_size=30 * 24,
        max_size=30 * 24,
    )
)
@settings(max_examples=50)
def test_tou_total_independent_of_decomposition(load: list[Decimal]) -> None:
    # The TOU energy charge equals off-peak kWh * off rate + peak kWh * peak rate, computed
    # independently from the line items — a cross-check on the bucketing.
    result = estimate_bill(tou_tariff(), Usage(hourly_kwh=tuple(load)), JUNE)
    assert result.ok
    by_period: dict[int, Decimal] = {}
    for li in result.line_items:
        if li.period >= 0:
            by_period[li.period] = by_period.get(li.period, Decimal(0)) + li.kwh
    recomputed = by_period.get(0, Decimal(0)) * Decimal("0.10") + by_period.get(
        1, Decimal(0)
    ) * Decimal("0.30")
    assert result.energy_charge == recomputed


@given(usage=kwh)
def test_determinism_byte_identical_json(usage: Decimal) -> None:
    u = Usage(total_kwh=usage)
    first = json.dumps(estimate_bill(tiered_tariff(), u, JUNE).to_json(), sort_keys=True)
    second = json.dumps(estimate_bill(tiered_tariff(), u, JUNE).to_json(), sort_keys=True)
    assert first == second


@given(
    rate=st.decimals(min_value=0, max_value=2, places=5, allow_nan=False, allow_infinity=False),
    boundary=st.decimals(
        min_value=1, max_value=1000, places=0, allow_nan=False, allow_infinity=False
    ),
    usage=kwh,
)
@settings(max_examples=100)
def test_two_tier_never_cheaper_than_first_tier_rate(
    rate: Decimal, boundary: Decimal, usage: Decimal
) -> None:
    # With a higher second-tier rate, the bill is always >= pricing everything at tier 1.
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(
                    tiers=(
                        EnergyTier(rate=rate, max=boundary),
                        EnergyTier(rate=rate + Decimal("0.05")),
                    )
                ),
            )
        ),
        schedule=flat_schedule(),
    )
    result = estimate_bill(tariff, Usage(total_kwh=usage), JUNE)
    assert result.energy_charge >= usage * rate
