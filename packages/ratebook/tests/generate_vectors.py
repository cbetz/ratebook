"""Regenerate the cross-engine golden bill vectors.

Run: ``uv run python packages/ratebook/tests/generate_vectors.py``

Writes ``tests/vectors/v0_bills.json`` — the language-agnostic oracle that BOTH the Python
engine (``test_vectors.py``) and the TypeScript port must reproduce byte-for-byte. The cases
deliberately exercise the paths most likely to diverge between two implementations:
boundary-crossing tiers, TOU hourly bucketing, the minimum-charge floor, kWh-daily cap scaling,
$/day fixed proration, the identical-ladder aggregate shortcut, signed fixed charges, and a
typed refusal. Decimal-as-string keeps the expected values identical across languages.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ratebook import (
    BillingWindow,
    EnergyPeriod,
    EnergyRateStructure,
    EnergyTier,
    FixedCharge,
    FixedChargeUnit,
    MinCharge,
    MinChargeUnit,
    Tariff,
    TierMaxUnit,
    UnsupportedFeature,
    UnsupportedKind,
    Usage,
    estimate_bill,
)

from conftest import (
    flat_schedule,
    peco_rate_r,
    seasonal_tariff,
    tiered_tariff,
    tou_schedule,
    tou_tariff,
)


def _single(tiers, schedule=None, **kw) -> Tariff:
    return Tariff(
        energy=EnergyRateStructure(periods=(EnergyPeriod(tiers=tiers),)),
        schedule=schedule or flat_schedule(),
        **kw,
    )


def _case(name, tariff, usage, window):
    result = estimate_bill(tariff, usage, window)
    if usage.hourly_kwh is not None:
        u = {"hourly_kwh": [str(x) for x in usage.hourly_kwh]}
    else:
        u = {"total_kwh": str(usage.total_kwh)}
    return {
        "name": name,
        "tariff": tariff.to_json(),
        "usage": u,
        "window": window.to_json(),
        "expected": result.to_json(),
    }


def build_cases() -> list[dict]:
    w30 = BillingWindow(date(2025, 6, 1), 30)
    cases = [
        _case("peco_rate_r_flat_900kwh", peco_rate_r(), Usage.aggregate(900), w30),
        _case("tiered_800kwh_crosses_boundary", tiered_tariff(), Usage.aggregate(800), w30),
        _case("seasonal_summer_1000kwh", seasonal_tariff(), Usage.aggregate(1000), w30),
        # TOU hourly bucketing: Jun 2-3 2025 are Mon/Tue (weekday peak 16-20).
        _case(
            "tou_2day_hourly",
            tou_tariff(),
            Usage.hourly([1.0] * 48),
            BillingWindow(date(2025, 6, 2), 2),
        ),
        # Minimum-charge floor applied (energy + fixed below the floor).
        _case(
            "min_charge_floor_applied",
            _single(
                (EnergyTier(rate=Decimal("0.10")),),
                min_charge=MinCharge(Decimal("25.00"), MinChargeUnit.PER_MONTH),
            ),
            Usage.aggregate(100),
            w30,
        ),
        # kWh-daily tier cap scales by window days (10 kWh/day * 30 = 300 kWh first tier).
        _case(
            "kwh_daily_tier_scaling",
            _single(
                (
                    EnergyTier(
                        rate=Decimal("0.05"), max=Decimal("10"), max_unit=TierMaxUnit.KWH_DAILY
                    ),
                    EnergyTier(rate=Decimal("0.20")),
                )
            ),
            Usage.aggregate(400),
            w30,
        ),
        # $/day fixed proration over a 28-day window.
        _case(
            "fixed_daily_proration",
            _single(
                (EnergyTier(rate=Decimal("0.10")),),
                fixed_charges=(FixedCharge(Decimal("0.50"), FixedChargeUnit.PER_DAY),),
            ),
            Usage.aggregate(100),
            BillingWindow(date(2025, 6, 1), 28),
        ),
        # Identical-ladder TOU: aggregate is sufficient because both periods price the same.
        _case(
            "identical_ladder_tou_aggregate",
            Tariff(
                energy=EnergyRateStructure(
                    periods=(
                        EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.106929")),)),
                        EnergyPeriod(tiers=(EnergyTier(rate=Decimal("0.106929")),)),
                    )
                ),
                schedule=tou_schedule(),
            ),
            Usage.aggregate(800),
            w30,
        ),
        # Signed (negative) fixed charge — a credit.
        _case(
            "negative_fixed_credit",
            _single(
                (EnergyTier(rate=Decimal("0.10")),),
                fixed_charges=(
                    FixedCharge(Decimal("10.00"), FixedChargeUnit.PER_MONTH),
                    FixedCharge(Decimal("-3.00"), FixedChargeUnit.PER_MONTH),
                ),
            ),
            Usage.aggregate(100),
            w30,
        ),
        # Typed refusal: a demand charge makes the bill unpriceable (ok=false).
        _case(
            "demand_charge_refused",
            _single(
                (EnergyTier(rate=Decimal("0.10")),),
                unsupported=(UnsupportedFeature(UnsupportedKind.DEMAND_CHARGE, "12 $/kW"),),
            ),
            Usage.aggregate(100),
            w30,
        ),
    ]
    return cases


def main() -> None:
    out = {
        "schema_version": 0,
        "description": (
            "Ratebook engine v0 golden bill vectors; shared by the Python engine and the "
            "TypeScript port so the two never diverge."
        ),
        "cases": build_cases(),
    }
    path = Path(__file__).parent / "vectors" / "v0_bills.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {path} with {len(out['cases'])} cases")
    for c in out["cases"]:
        e = c["expected"]
        print(f"  {c['name']:34} ok={e['ok']!s:5} total={e['total']}")


if __name__ == "__main__":
    main()
