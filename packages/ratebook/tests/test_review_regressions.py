"""Regressions for bugs found by the adversarial review (engine + schema + serialization)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from conftest import flat_schedule, tou_tariff
from ratebook import (
    BillingWindow,
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    MinCharge,
    MinChargeUnit,
    Tariff,
    TierMaxUnit,
    UnsupportedFeature,
    UnsupportedKind,
    Usage,
    estimate_bill,
    supported,
)
from ratebook.engine import RefusalReason
from ratebook.money import decimal_to_json

JUNE = BillingWindow(date(2025, 6, 1), 30)


def _single_period(tiers) -> Tariff:
    return Tariff(
        energy=EnergyRateStructure(periods=(EnergyPeriod(tiers=tiers),)), schedule=flat_schedule()
    )


# #2 — finite max on the final tier is treated as open (PySAM convention) but warns.
def test_finite_final_tier_max_warns_not_silent() -> None:
    tariff = _single_period((EnergyTier(rate=Decimal("0.10"), max=Decimal("16")),))
    result = estimate_bill(tariff, Usage.aggregate(1000), JUNE)
    assert result.ok
    assert result.energy_charge == Decimal("100.00")  # all 1000 kWh at the open top tier
    assert "usage_exceeds_final_tier_max" in result.warnings


def test_finite_final_tier_no_warning_when_under() -> None:
    tariff = _single_period((EnergyTier(rate=Decimal("0.10"), max=Decimal("2000")),))
    result = estimate_bill(tariff, Usage.aggregate(1000), JUNE)
    assert "usage_exceeds_final_tier_max" not in result.warnings


# #5 — a wrong-length hourly array is a caller bug and must raise even for a refusable tariff.
def test_hourly_length_mismatch_raises_even_for_refusable_tariff() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        unsupported=(UnsupportedFeature(UnsupportedKind.DEMAND_CHARGE, "x"),),
    )
    with pytest.raises(ValueError, match="hourly_kwh"):
        estimate_bill(tariff, Usage.hourly([1.0] * 10), JUNE)


# #6 — aggregate usage is sufficient when multiple periods price identically.
def test_aggregate_ok_when_periods_price_identically() -> None:
    # Two TOU periods with the SAME single-tier rate: total kWh fully determines the bill.
    same = (EnergyTier(rate=Decimal("0.106929")),)
    tariff = Tariff(
        energy=EnergyRateStructure(periods=(EnergyPeriod(tiers=same), EnergyPeriod(tiers=same))),
        schedule=tou_tariff().schedule,
    )
    result = estimate_bill(tariff, Usage.aggregate(800), JUNE)
    assert result.ok
    assert result.energy_charge == Decimal("800") * Decimal("0.106929")


def test_aggregate_still_refused_when_periods_differ() -> None:
    result = estimate_bill(tou_tariff(), Usage.aggregate(800), JUNE)
    assert not result.ok
    assert result.refusal.reason is RefusalReason.AGGREGATE_USAGE_MULTI_PERIOD


# #7 — supported() reflects the $/year-min single-window refusal.
def test_supported_flags_annual_min_in_single_window() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        min_charge=MinCharge(Decimal("100"), MinChargeUnit.PER_YEAR),
    )
    assert not supported(tariff).fully_supported
    assert supported(tariff, single_window=False).fully_supported  # estimate_annual handles it


# #8 — a DEMAND_NORMALIZED_TIER_MAX feature marker now refuses (and maps to its own reason).
def test_demand_normalized_feature_marker_refuses() -> None:
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),)
        ),
        schedule=flat_schedule(),
        unsupported=(UnsupportedFeature(UnsupportedKind.DEMAND_NORMALIZED_TIER_MAX, "x"),),
    )
    result = estimate_bill(tariff, Usage.aggregate(100), JUNE)
    assert not result.ok
    assert result.refusal.reason is RefusalReason.DEMAND_NORMALIZED_TIER_MAX
    assert not supported(tariff).fully_supported


# #9 — mixing tier-max units among bounded tiers is rejected at construction.
def test_mixed_unit_bounded_tiers_rejected() -> None:
    with pytest.raises(ValueError, match="mix max units"):
        EnergyPeriod(
            tiers=(
                EnergyTier(rate=Decimal("0.05"), max=Decimal("20"), max_unit=TierMaxUnit.KWH_DAILY),
                EnergyTier(rate=Decimal("0.10"), max=Decimal("100"), max_unit=TierMaxUnit.KWH),
                EnergyTier(rate=Decimal("0.20")),
            )
        )


def test_uniform_unit_bounded_tiers_allowed() -> None:
    # The open final tier's (default) unit does not count toward the mix check.
    EnergyPeriod(
        tiers=(
            EnergyTier(rate=Decimal("0.05"), max=Decimal("10"), max_unit=TierMaxUnit.KWH_DAILY),
            EnergyTier(rate=Decimal("0.10"), max=Decimal("20"), max_unit=TierMaxUnit.KWH_DAILY),
            EnergyTier(rate=Decimal("0.20")),
        )
    )


# #10 — canonical Decimal serialization: value-equal Decimals serialize byte-identically.
@pytest.mark.parametrize(
    "a,b",
    [("0.10", "0.1"), ("500", "500.0"), ("700.0", "700.00"), ("11.30", "11.3"), ("-3.00", "-3")],
)
def test_decimal_serialization_is_canonical(a: str, b: str) -> None:
    assert decimal_to_json(Decimal(a)) == decimal_to_json(Decimal(b))


def test_canonical_serialization_no_exponent_form() -> None:
    # normalize() would emit "7E+2"; we must stay in fixed-point.
    assert decimal_to_json(Decimal("700.0")) == "700"
    assert "E" not in decimal_to_json(Decimal("700.0"))


def test_differently_spelled_tariffs_serialize_identically() -> None:
    t1 = _single_period((EnergyTier(rate=Decimal("0.10"), max=Decimal("500.0")),))
    t2 = _single_period((EnergyTier(rate=Decimal("0.1"), max=Decimal("500")),))
    assert t1.to_json() == t2.to_json()
