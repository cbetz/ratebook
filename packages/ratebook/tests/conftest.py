"""Shared tariff builders for engine tests."""

from __future__ import annotations

from decimal import Decimal

from ratebook import (
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    FixedCharge,
    FixedChargeUnit,
    Schedule,
    Sector,
    Tariff,
    TariffIdentity,
)

ALL_ZERO_12x24 = tuple(tuple(0 for _ in range(24)) for _ in range(12))


def flat_schedule(period: int = 0) -> Schedule:
    row = tuple(period for _ in range(24))
    matrix = tuple(row for _ in range(12))
    return Schedule(weekday=matrix, weekend=matrix)


def peco_rate_r() -> Tariff:
    """PECO Residential Rate R as it reads in the corpus: one period, one open tier at
    0.20513 + 0.01371 $/kWh, $11.30/month fixed charge."""
    return Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.20513"), adj=Decimal("0.01371")),)),
            )
        ),
        schedule=flat_schedule(),
        fixed_charges=(FixedCharge(Decimal("11.30"), FixedChargeUnit.PER_MONTH),),
        identity=TariffIdentity(
            plan_code="R", plan_name="Residential Service", sector=Sector.RESIDENTIAL
        ),
    )


def tiered_tariff() -> Tariff:
    """One period, two tiers: first 500 kWh at $0.10, remainder at $0.15."""
    return Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(
                    tiers=(
                        EnergyTier(rate=Decimal("0.10"), max=Decimal("500")),
                        EnergyTier(rate=Decimal("0.15")),
                    )
                ),
            )
        ),
        schedule=flat_schedule(),
        identity=TariffIdentity(sector=Sector.RESIDENTIAL),
    )


def tou_schedule(peak_period: int = 1, offpeak_period: int = 0) -> Schedule:
    """Weekday hours 16-20 are peak; everything else off-peak. Weekends all off-peak."""
    weekday_row = tuple(peak_period if 16 <= h < 21 else offpeak_period for h in range(24))
    offpeak_row = tuple(offpeak_period for _ in range(24))
    return Schedule(
        weekday=tuple(weekday_row for _ in range(12)),
        weekend=tuple(offpeak_row for _ in range(12)),
    )


def tou_tariff() -> Tariff:
    """Two periods (off-peak $0.10, peak $0.30), each a single open tier."""
    return Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10")),)),
                EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.30")),)),
            )
        ),
        schedule=tou_schedule(),
        identity=TariffIdentity(sector=Sector.RESIDENTIAL),
    )


def seasonal_schedule(winter_period: int = 0, summer_period: int = 1) -> Schedule:
    """Months Jun-Sep (6-9) use the summer period; the rest winter. No intra-day variation."""

    def row_for(month_idx: int) -> tuple[int, ...]:
        period = summer_period if 5 <= month_idx <= 8 else winter_period
        return tuple(period for _ in range(24))

    matrix = tuple(row_for(m) for m in range(12))
    return Schedule(weekday=matrix, weekend=matrix)


def seasonal_tariff() -> Tariff:
    return Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.11")),)),
                EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.18")),)),
            )
        ),
        schedule=seasonal_schedule(),
        identity=TariffIdentity(sector=Sector.RESIDENTIAL),
    )
