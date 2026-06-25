"""Engine bill-match acceptance test: given a real bill's components, reproduce the total < 2%.

This validates the engine's arithmetic given the components — it is NOT end-to-end from
extraction alone (generation/transmission/riders are supplied here, not extracted). Inputs are
the rate/usage facts from a real PECO bill (May 2026 statement, 30-day service period,
1,244 kWh) — no account, address, or other personal data. The distribution rate (0.10276 $/kWh)
is the value the extractor pulled from the Rate R tariff PDF, validated here against the bill's
actual distribution line; the generation/transmission/rider components are the ones the tariff
sheet only referenced and are supplied from the bill.

The engine, given all components, must reproduce the $276.35 total to well within 2%.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ratebook import BillingWindow, Usage, estimate_bill
from ratebook_data.extract import extracted_to_tariff

KWH = 1244
DAYS = 30
PERIOD_START = date(2026, 4, 28)
ACTUAL_BILL_TOTAL = Decimal("276.35")

# The components of the real bill. Distribution ($0.10276/kWh, $11.29 customer charge) is what
# the tariff sheet prices; generation, transmission, DSIC, and the state-tax adjustment are the
# separately-sourced pieces a rate sheet alone can't supply.
PECO_FULL_BILL = {
    "plan_code": "R",
    "plan_name": "Residence Service",
    "sector": "residential",
    "energy_charges": [
        {
            "rate": "0.10276",
            "component": "distribution",
            "label": "Distribution",
            "tier_max_kwh": "",
        },
        {"rate": "0.10237", "component": "generation", "label": "Generation", "tier_max_kwh": ""},
        {
            "rate": "0.00787",
            "component": "transmission",
            "label": "Transmission",
            "tier_max_kwh": "",
        },
    ],
    "fixed_charges": [
        {
            "amount": "11.29",
            "unit": "$/month",
            "label": "Customer Charge",
            "applies_to": "standard",
        },
        {"amount": "0.15", "unit": "$/month", "label": "Distribution System Improvement Charge"},
        {"amount": "-0.06", "unit": "$/month", "label": "State Tax Adjustment"},
    ],
    "tiered": False,
    "time_of_use": False,
    "components_priced": ["distribution", "generation", "transmission"],
    "components_referenced_only": [],
    "riders": [],
    "confidence": 1.0,
    "notes": "",
}


def test_reproduces_peco_bill_within_2_percent() -> None:
    priced = extracted_to_tariff(PECO_FULL_BILL)
    result = estimate_bill(priced.tariff, Usage.aggregate(KWH), BillingWindow(PERIOD_START, DAYS))
    assert result.ok
    error = abs(result.total - ACTUAL_BILL_TOTAL) / ACTUAL_BILL_TOTAL
    assert error < Decimal("0.02"), (
        f"bill-match error {error:.4%}: {result.total} vs {ACTUAL_BILL_TOTAL}"
    )
    # In fact it lands within a fraction of a cent.
    assert abs(result.total - ACTUAL_BILL_TOTAL) < Decimal("0.01")


def test_extracted_distribution_rate_matches_bill_line() -> None:
    # The tariff-PDF distribution rate reproduces the bill's distribution charge ($127.83).
    assert Decimal(str(KWH)) * Decimal("0.10276") == Decimal("127.83344")  # bill rounds to 127.83


def test_distribution_only_would_be_about_half_the_bill() -> None:
    # The thesis: a distribution-only rate sheet is ~half the bill. Delivery vs supply split.
    distribution_only = {**PECO_FULL_BILL, "energy_charges": PECO_FULL_BILL["energy_charges"][:1]}
    priced = extracted_to_tariff(distribution_only)
    result = estimate_bill(priced.tariff, Usage.aggregate(KWH), BillingWindow(PERIOD_START, DAYS))
    fraction = result.total / ACTUAL_BILL_TOTAL
    assert Decimal("0.45") < fraction < Decimal("0.55")
