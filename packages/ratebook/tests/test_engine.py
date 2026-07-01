"""Unit tests for the rate engine: the concrete bill arithmetic and refusal behavior."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from ratebook import (
    BillingWindow,
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    MinCharge,
    MinChargeUnit,
    Schedule,
    Tariff,
    TierMaxUnit,
    UnsupportedFeature,
    UnsupportedKind,
    Usage,
    estimate_bill,
    supported,
)
from ratebook.engine import RefusalReason

from conftest import (
    flat_schedule,
    peco_rate_r,
    seasonal_tariff,
    tiered_tariff,
    tou_tariff,
)

JUNE = BillingWindow(date(2025, 6, 1), 30)


def test_flat_bill_closed_form() -> None:
    result = estimate_bill(peco_rate_r(), Usage.aggregate(900), JUNE)
    assert result.ok
    # 900 * (0.20513 + 0.01371) + 11.30
    assert result.energy_charge == Decimal("900") * Decimal("0.21884")
    assert result.fixed_charge == Decimal("11.30")
    assert result.total == Decimal("900") * Decimal("0.21884") + Decimal("11.30")


def test_tiered_bill_crosses_tier_boundary() -> None:
    # 800 kWh: 500 @ 0.10 + 300 @ 0.15 = 50 + 45 = 95
    result = estimate_bill(tiered_tariff(), Usage.aggregate(800), JUNE)
    assert result.ok
    assert result.energy_charge == Decimal("95.00")
    energy_items = [li for li in result.line_items if li.period >= 0]
    assert len(energy_items) == 2
    assert energy_items[0].kwh == Decimal("500")
    assert energy_items[1].kwh == Decimal("300")


def test_tiered_bill_within_first_tier() -> None:
    result = estimate_bill(tiered_tariff(), Usage.aggregate(300), JUNE)
    assert result.energy_charge == Decimal("30.00")
    assert len([li for li in result.line_items if li.period >= 0]) == 1


def test_tou_requires_hourly_usage() -> None:
    result = estimate_bill(tou_tariff(), Usage.aggregate(900), JUNE)
    assert not result.ok
    assert result.total is None
    assert result.refusal.reason is RefusalReason.AGGREGATE_USAGE_MULTI_PERIOD


def test_tou_hourly_buckets_by_period() -> None:
    # 1 kWh every hour for 30 days. Peak = weekday hours 16-20 (5 hours/day).
    load = [1.0] * (30 * 24)
    result = estimate_bill(tou_tariff(), Usage.hourly(load), JUNE)
    assert result.ok
    # Count weekday peak hours in June 2025.
    peak_hours = sum(5 for d in JUNE.iter_days() if d.weekday() < 5)
    total_hours = 30 * 24
    offpeak_hours = total_hours - peak_hours
    expected = Decimal(offpeak_hours) * Decimal("0.10") + Decimal(peak_hours) * Decimal("0.30")
    assert result.energy_charge == expected


def test_seasonal_aggregate_ok_within_one_season() -> None:
    # A June window is entirely in the summer period -> single effective period -> aggregate ok.
    result = estimate_bill(seasonal_tariff(), Usage.aggregate(1000), JUNE)
    assert result.ok
    assert result.energy_charge == Decimal("1000") * Decimal("0.18")


def test_seasonal_aggregate_refused_across_boundary() -> None:
    # A window spanning late May into June crosses winter->summer -> two periods -> refuse.
    window = BillingWindow(date(2025, 5, 20), 20)
    result = estimate_bill(seasonal_tariff(), Usage.aggregate(1000), window)
    assert not result.ok
    assert result.refusal.reason is RefusalReason.AGGREGATE_USAGE_MULTI_PERIOD


def test_fixed_charge_daily_proration() -> None:
    from ratebook import FixedCharge, FixedChargeUnit

    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        fixed_charges=(FixedCharge(Decimal("0.50"), FixedChargeUnit.PER_DAY),),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), BillingWindow(date(2025, 6, 1), 28))
    assert result.fixed_charge == Decimal("0.50") * Decimal("28")


def test_kwh_daily_tier_max_scales_with_days() -> None:
    # First tier: 10 kWh/day at $0.05; remainder at $0.20. 30-day window -> 300 kWh first tier.
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(
                    tiers=(
                        EnergyTier(
                            rate=Decimal("0.05"), max=Decimal("10"), max_unit=TierMaxUnit.KWH_DAILY
                        ),
                        EnergyTier(rate=Decimal("0.20")),
                    )
                ),
            )
        ),
        schedule=flat_schedule(),
    )
    result = estimate_bill(tariff, Usage.aggregate(400), BillingWindow(date(2025, 6, 1), 30))
    # 300 @ 0.05 + 100 @ 0.20 = 15 + 20 = 35
    assert result.energy_charge == Decimal("35.00")


def test_min_charge_floor_applied() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        min_charge=MinCharge(Decimal("25.00"), MinChargeUnit.PER_MONTH),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)  # energy = $10
    assert result.min_charge_floor_applied
    assert result.total == Decimal("25.00")


def test_min_charge_not_applied_above_floor() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        min_charge=MinCharge(Decimal("25.00"), MinChargeUnit.PER_MONTH),
    )
    result = estimate_bill(tariff, Usage.aggregate(500), JUNE)  # energy = $50
    assert not result.min_charge_floor_applied
    assert result.total == Decimal("50.00")


def test_annual_min_refused_in_single_window() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        min_charge=MinCharge(Decimal("120.00"), MinChargeUnit.PER_YEAR),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)
    assert not result.ok
    assert result.refusal.reason is RefusalReason.ANNUAL_MIN_SINGLE_WINDOW


def test_demand_charge_refused() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        unsupported=(UnsupportedFeature(UnsupportedKind.DEMAND_CHARGE, "12 $/kW"),),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)
    assert not result.ok
    assert result.refusal.reason is RefusalReason.DEMAND_CHARGE
    assert not supported(tariff).fully_supported


def test_demand_normalized_tier_max_refused() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(
                    tiers=(
                        EnergyTier(
                            rate=Decimal("0.10"),
                            max=Decimal("100"),
                            max_unit=TierMaxUnit.KWH_PER_KW,
                        ),
                        EnergyTier(rate=Decimal("0.20")),
                    )
                ),
            )
        ),
        schedule=flat_schedule(),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)
    assert not result.ok
    assert result.refusal.reason is RefusalReason.DEMAND_NORMALIZED_TIER_MAX


def test_negative_fixed_charge_credit() -> None:
    from ratebook import FixedCharge, FixedChargeUnit

    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        fixed_charges=(
            FixedCharge(Decimal("10.00"), FixedChargeUnit.PER_MONTH),
            FixedCharge(Decimal("-3.00"), FixedChargeUnit.PER_MONTH),
        ),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)
    assert result.fixed_charge == Decimal("7.00")


def test_hourly_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="hourly_kwh"):
        estimate_bill(tou_tariff(), Usage.hourly([1.0] * 10), JUNE)


def test_sell_rate_warns_not_refuses() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10"), sell=Decimal("0.05")),)),)
        ),
        schedule=flat_schedule(),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)
    assert result.ok
    assert "sell_rate_not_modeled" in result.warnings


def test_malformed_tariff_raises_at_construction() -> None:
    with pytest.raises(ValueError, match="strictly increase"):
        EnergyPeriod(
            tiers=(
                EnergyTier(rate=Decimal("0.10"), max=Decimal("3000")),
                EnergyTier(rate=Decimal("0.20"), max=Decimal("200")),
            )
        )


def test_schedule_wrong_shape_raises() -> None:
    with pytest.raises(ValueError, match="24 hours"):
        Schedule(
            weekday=tuple(tuple(0 for _ in range(23)) for _ in range(12)),
            weekend=tuple(tuple(0 for _ in range(24)) for _ in range(12)),
        )


def test_schedule_out_of_range_period_raises() -> None:
    with pytest.raises(ValueError, match="out of range"):
        Tariff(
            energy=EnergyRateStructure(
                periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
            ),
            schedule=flat_schedule(period=3),  # only period 0 exists
        )
