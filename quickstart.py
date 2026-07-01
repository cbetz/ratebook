"""Ratebook quickstart: price a flat residential tariff with the engine — no data download.

Run with:  uv run python quickstart.py
"""

from datetime import date
from decimal import Decimal

from ratebook import (
    BillingWindow,
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    FixedCharge,
    FixedChargeUnit,
    Schedule,
    Sector,
    Tariff,
    TariffIdentity,
    Usage,
    estimate_bill,
)

# A flat residential tariff: $0.10276/kWh + $11.30/month (PECO Rate R distribution).
no_tou = tuple(tuple(0 for _ in range(24)) for _ in range(12))  # 12 months x 24 hours, one period
tariff = Tariff(
    energy=EnergyRateStructure(
        periods=(EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.10276")),)),)
    ),
    schedule=Schedule(weekday=no_tou, weekend=no_tou),
    identity=TariffIdentity(
        plan_code="R", plan_name="Example flat residential", sector=Sector.RESIDENTIAL
    ),
    fixed_charges=(FixedCharge(Decimal("11.30"), FixedChargeUnit.PER_MONTH),),
)

bill = estimate_bill(tariff, Usage.aggregate(1244), BillingWindow(date(2026, 4, 28), 30))
print(f"ok={bill.ok}  total=${bill.total}")  # ok=True  total=$139.13344
