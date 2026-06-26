"""Cross-validate the Ratebook engine against PySAM utilityrate5 on real URDB tariffs.

Skipped entirely if PySAM is not installed (``uv sync --group validation`` to enable). Energy
charge and fixed charge are asserted *separately* per month so a tier-vs-fixed offset cannot
cancel. Agreement target: < $0.02 per month / < $0.05 annual (PySAM uses C doubles, the engine
uses Decimal; the gap is float noise, not a modeling difference).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySAM", reason="nrel-pysam not installed (uv sync --group validation)")

from pysam_oracle import PYSAM_YEAR, run_pysam, shaped_load_8760
from ratebook import Tariff, estimate_annual, supported

# The validation tariffs are committed as JSON fixtures (generated from the URDB corpus via
# corpus.load_tariff), so this cross-validation runs in CI without building the full corpus.
FIXTURES = Path(__file__).parent / "fixtures" / "tariffs"

# Real URDB residential tariffs spanning every structure class the v0 engine supports.
# (label, description) — verified fully-supported and $/month-fixed during corpus scan.
CASES = [
    ("69e65026bc32447e430e25a9", "PECO Rate R (flat, the bill-match target)"),
    ("539f6a0aec4f024411ec8acd", "Blue Ridge EMC Residential (flat)"),
    ("539f6a0aec4f024411ec8ad1", "Charles Mix Electric Rate D (tiered)"),
    ("539f6a33ec4f024411ec8c45", "City of Wellington Rural Residential (seasonal)"),
    ("539f6a0aec4f024411ec8acb", "Delaware Electric Coop Space Heating (seasonal+tiered)"),
    ("539f6a23ec4f024411ec8be1", "Broad River Electric Code 80 (TOU)"),
    ("539f6abbec4f024411ec9349", "North Central Elec Coop Residential TOD (TOU+tiered)"),
]

ABS_TOL_MONTH = 0.02
ABS_TOL_ANNUAL = 0.05


@pytest.fixture(scope="module")
def load() -> list[float]:
    return shaped_load_8760()


@pytest.mark.parametrize("label,description", CASES, ids=[c[1] for c in CASES])
def test_engine_matches_pysam(label: str, description: str, load: list[float]) -> None:
    tariff = Tariff.from_json(json.loads((FIXTURES / f"{label}.json").read_text()))
    assert supported(tariff).fully_supported, f"{description} is not fully supported"

    annual = estimate_annual(tariff, load, PYSAM_YEAR)
    assert annual.ok

    ref = run_pysam(tariff, load)

    # Per-month energy charge.
    months_energy = zip(annual.windows, ref["monthly_energy"], strict=True)
    for month, (mine, theirs) in enumerate(months_energy, 1):
        assert abs(float(mine.energy_charge) - theirs) < ABS_TOL_MONTH, (
            f"{description} month {month}: engine {mine.energy_charge} vs PySAM {theirs}"
        )

    # Per-month fixed charge.
    months_fixed = zip(annual.windows, ref["monthly_fixed"], strict=True)
    for month, (mine, theirs) in enumerate(months_fixed, 1):
        assert abs(float(mine.fixed_charge) - theirs) < ABS_TOL_MONTH, (
            f"{description} month {month}: fixed {mine.fixed_charge} vs PySAM {theirs}"
        )

    # Annual total.
    assert abs(float(annual.total) - ref["annual_total"]) < ABS_TOL_ANNUAL, (
        f"{description}: engine annual {annual.total} vs PySAM {ref['annual_total']}"
    )


def test_kwh_daily_weekday_split_matches_pysam(load: list[float]) -> None:
    """Regression for the kWh-daily active-days fix: a weekday/weekend split with daily caps
    must scale each period's cap by the days that period is active (weekdays vs weekends), not
    the whole month. This is the intra-month multi-period case the bug corrupted in annual mode.
    """
    from decimal import Decimal

    from ratebook import (
        EnergyPeriod,
        EnergyRateStructure,
        EnergyTier,
        Schedule,
        Tariff,
        TierMaxUnit,
    )

    weekday = tuple(tuple(0 for _ in range(24)) for _ in range(12))
    weekend = tuple(tuple(1 for _ in range(24)) for _ in range(12))
    tariff = Tariff(
        energy=EnergyRateStructure(
            periods=(
                EnergyPeriod(
                    tiers=(
                        EnergyTier(
                            Decimal("0.08"), max=Decimal("15"), max_unit=TierMaxUnit.KWH_DAILY
                        ),
                        EnergyTier(Decimal("0.16")),
                    )
                ),
                EnergyPeriod(
                    tiers=(
                        EnergyTier(
                            Decimal("0.05"), max=Decimal("15"), max_unit=TierMaxUnit.KWH_DAILY
                        ),
                        EnergyTier(Decimal("0.10")),
                    )
                ),
            )
        ),
        schedule=Schedule(weekday=weekday, weekend=weekend),
    )
    annual = estimate_annual(tariff, load, PYSAM_YEAR)
    ref = run_pysam(tariff, load)
    for month, (mine, theirs) in enumerate(
        zip(annual.windows, ref["monthly_energy"], strict=True), 1
    ):
        assert abs(float(mine.energy_charge) - theirs) < ABS_TOL_MONTH, (
            f"month {month}: engine {mine.energy_charge} vs PySAM {theirs}"
        )
