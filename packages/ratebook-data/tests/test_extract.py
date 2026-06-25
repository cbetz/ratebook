"""Eval-harness tests for the extraction converter + grader (deterministic, no API).

These exercise the path that turns a structured extraction into a priceable Tariff and grades
it, using the known-correct PECO Rate R values from the tariff sheet (Supplement 21, eff.
2026-01-01): distribution $0.10276/kWh, fixed $11.30/month, min = fixed; generation and
transmission referenced but priced elsewhere.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ratebook import BillingWindow, Usage, estimate_bill
from ratebook_data.extract import (
    EXTRACTION_SCHEMA,
    extracted_to_tariff,
    grade_extraction,
)

# The structured extraction a correct extractor produces from the PECO Rate R distribution sheet.
PECO_EXTRACTION = {
    "plan_code": "R",
    "plan_name": "Residence Service",
    "sector": "residential",
    "effective_date": "2026-01-01",
    "fixed_charges": [
        {"amount": "11.30", "unit": "$/month", "label": "Fixed Distribution Service Charge"}
    ],
    "energy_charges": [
        {
            "rate": "0.10276",
            "component": "distribution",
            "label": "Variable Distribution Service Charge",
            "tier_max_kwh": "",
        }
    ],
    "min_charge": {
        "amount": "11.30",
        "unit": "$/month",
        "basis": "equals fixed distribution charge",
    },
    "tiered": False,
    "time_of_use": False,
    "components_priced": ["distribution"],
    "components_referenced_only": [
        "generation (Generation Supply Adjustment Procurement Class 1)",
        "transmission (Transmission Service Charge)",
    ],
    "riders": [
        "State Tax Adjustment Clause",
        "Distribution System Improvement Charge (DSIC)",
        "Universal Service Fund Charge",
    ],
    "confidence": 0.97,
    "notes": "Distribution component only; a full bill also needs generation/transmission/riders.",
}

PECO_GOLDEN = {"distribution_rate": "0.10276", "fixed_charge": "11.30", "min_charge": "11.30"}


def test_extracted_to_tariff_prices_distribution() -> None:
    priced = extracted_to_tariff(PECO_EXTRACTION)
    tariff = priced.tariff
    assert tariff.energy.periods[0].tiers[0].effective_rate == Decimal("0.10276")
    assert tariff.fixed_charges[0].amount == Decimal("11.30")
    assert tariff.min_charge.amount == Decimal("11.30")
    assert priced.priced_components == ("distribution",)
    assert any("generation" in m for m in priced.missing_components)
    assert any("transmission" in m for m in priced.missing_components)


def test_distribution_bill_is_computable() -> None:
    priced = extracted_to_tariff(PECO_EXTRACTION)
    # 600 kWh distribution-only: 600 * 0.10276 + 11.30 = 72.956
    result = estimate_bill(priced.tariff, Usage.aggregate(600), BillingWindow(date(2026, 1, 1), 31))
    assert result.ok
    assert result.energy_charge == Decimal("600") * Decimal("0.10276")
    assert result.total == Decimal("600") * Decimal("0.10276") + Decimal("11.30")


def test_grade_passes_on_correct_extraction() -> None:
    priced = extracted_to_tariff(PECO_EXTRACTION)
    report = grade_extraction(priced, golden=PECO_GOLDEN)
    assert report.passed
    assert report.arithmetic_issues == []
    assert report.field_accuracy == 1.0


def test_grade_catches_wrong_rate() -> None:
    bad = {
        **PECO_EXTRACTION,
        "energy_charges": [{"rate": "0.21884", "component": "distribution", "label": "x"}],
    }
    report = grade_extraction(extracted_to_tariff(bad), golden=PECO_GOLDEN)
    assert not report.passed
    assert report.field_accuracy < 1.0


def test_summed_components_make_a_bundled_tier() -> None:
    # If distribution + generation + transmission are all priced at one tier, they sum.
    bundled = {
        **PECO_EXTRACTION,
        "energy_charges": [
            {"rate": "0.10276", "component": "distribution", "label": "d", "tier_max_kwh": ""},
            {"rate": "0.09", "component": "generation", "label": "g", "tier_max_kwh": ""},
            {"rate": "0.02", "component": "transmission", "label": "t", "tier_max_kwh": ""},
        ],
        "components_priced": ["distribution", "generation", "transmission"],
        "components_referenced_only": [],
    }
    priced = extracted_to_tariff(bundled)
    assert priced.tariff.energy.periods[0].tiers[0].effective_rate == Decimal("0.21276")


# The extraction from the PECO sheet lists BOTH fixed charges; the deterministic validator
# flagged that they are mutually exclusive. The converter must apply only the standard $11.30.
PECO_EXTRACTION_TWO_FIXED = {
    **PECO_EXTRACTION,
    "fixed_charges": [
        {"amount": "11.30", "unit": "$/month", "label": "Fixed Distribution Service Charge"},
        {
            "amount": "2.19",
            "unit": "$/month",
            "label": "Fixed Distribution Service Charge for Former Off-Peak Meters",
        },
    ],
}


def test_mutually_exclusive_fixed_charge_not_summed() -> None:
    priced = extracted_to_tariff(PECO_EXTRACTION_TWO_FIXED)
    assert len(priced.tariff.fixed_charges) == 1
    assert priced.tariff.fixed_charges[0].amount == Decimal("11.30")  # not 11.30 + 2.19


def test_applies_to_alternative_is_excluded() -> None:
    extraction = {
        **PECO_EXTRACTION,
        "fixed_charges": [
            {
                "amount": "11.30",
                "unit": "$/month",
                "label": "Customer Charge",
                "applies_to": "standard",
            },
            {
                "amount": "2.19",
                "unit": "$/month",
                "label": "Special meter",
                "applies_to": "alternative",
            },
        ],
    }
    priced = extracted_to_tariff(extraction)
    assert [str(c.amount) for c in priced.tariff.fixed_charges] == ["11.30"]


def test_extraction_schema_is_strict() -> None:
    # The schema must forbid extra keys (Anthropic strict structured outputs).
    assert EXTRACTION_SCHEMA["additionalProperties"] is False
    assert "energy_charges" in EXTRACTION_SCHEMA["required"]
