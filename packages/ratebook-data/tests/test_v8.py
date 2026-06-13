"""Tests for the URDB CSV-row → v8 JSON un-flattener."""

from __future__ import annotations

import json

from ratebook.urdb import tariff_from_v8
from ratebook_data.v8 import row_to_v8

FLAT_SCHEDULE = json.dumps([[0] * 24 for _ in range(12)])


def _peco_like_row() -> dict:
    return {
        "label": "abc123",
        "name": "Residential Service (R)",
        "utility": "PECO Energy Co",
        "eiaid": "14940.0",
        "sector": "Residential",
        "startdate": "2026-01-01 01:00:00",
        "enddate": "",
        "latest_update": "2026-04-20 10:22:25",
        "fixedchargefirstmeter": "11.3",
        "fixedchargeunits": "$/month",
        "energyratestructure/period0/tier0rate": "0.20513",
        "energyratestructure/period0/tier0adj": "0.01371",
        "energyratestructure/period0/tier0unit": "kWh",
        "energyweekdayschedule": FLAT_SCHEDULE,
        "energyweekendschedule": FLAT_SCHEDULE,
        # Empty cells must be ignored, not produce phantom tiers.
        "energyratestructure/period0/tier1rate": "",
        "demandratestructure/period0/tier0rate": "",
    }


def test_row_to_v8_nests_energy_structure() -> None:
    v8 = row_to_v8(_peco_like_row())
    assert v8["energyratestructure"] == [[{"rate": "0.20513", "adj": "0.01371", "unit": "kWh"}]]
    assert len(v8["energyweekdayschedule"]) == 12
    assert v8["fixedchargefirstmeter"] == "11.3"
    # No demand structure should be produced from an all-empty demand column.
    assert "demandratestructure" not in v8 or not any(
        t.get("rate") for p in v8["demandratestructure"] for t in p
    )


def test_tariff_from_row_round_trips_to_engine() -> None:
    tariff = tariff_from_v8(row_to_v8(_peco_like_row()))
    assert tariff.identity.eiaid == 14940  # ".0" artifact stripped
    assert tariff.identity.plan_name == "Residential Service (R)"
    assert len(tariff.energy.periods) == 1
    assert len(tariff.energy.periods[0].tiers) == 1
    assert tariff.energy.periods[0].tiers[0].effective_rate.__str__() == "0.21884"
    assert tariff.fixed_charges[0].amount.__str__() == "11.3"
    assert tariff.effective_range.start.isoformat() == "2026-01-01"


def test_adj_only_demand_charge_is_carried_as_unsupported() -> None:
    # A demand charge living only in the adj column (rate=0) must still be flagged, not dropped.
    from ratebook import supported
    from ratebook.schema import UnsupportedKind

    row = {
        "energyweekdayschedule": FLAT_SCHEDULE,
        "energyweekendschedule": FLAT_SCHEDULE,
        "energyratestructure/period0/tier0rate": "0.20",
        "flatdemandstructure/period0/tier0rate": "0",
        "flatdemandstructure/period0/tier0adj": "8.50",
    }
    tariff = tariff_from_v8(row_to_v8(row))
    kinds = {f.kind for f in tariff.unsupported}
    assert UnsupportedKind.FLAT_DEMAND in kinds
    assert not supported(tariff).fully_supported


def test_two_digit_year_enddate_recovered() -> None:
    # "24-12-30" is a real URDB enddate spelling; it must import as 2024, not be dropped to
    # None (which would make an ended tariff read as active).
    row = {
        "energyweekdayschedule": FLAT_SCHEDULE,
        "energyweekendschedule": FLAT_SCHEDULE,
        "energyratestructure/period0/tier0rate": "0.20",
        "startdate": "2023-01-01 00:00:00",
        "enddate": "24-12-30 23:59:56",
    }
    tariff = tariff_from_v8(row_to_v8(row))
    assert tariff.effective_range.end is not None
    assert tariff.effective_range.end.year == 2024


def test_multi_tier_multi_period_unflatten() -> None:
    row = {
        "energyweekdayschedule": json.dumps([[1] * 24 for _ in range(12)]),
        "energyweekendschedule": json.dumps([[0] * 24 for _ in range(12)]),
        "energyratestructure/period0/tier0rate": "0.10",
        "energyratestructure/period0/tier0max": "500",
        "energyratestructure/period0/tier1rate": "0.15",
        "energyratestructure/period1/tier0rate": "0.30",
    }
    v8 = row_to_v8(row)
    assert len(v8["energyratestructure"]) == 2
    assert len(v8["energyratestructure"][0]) == 2
    tariff = tariff_from_v8(v8)
    assert tariff.energy.periods[0].tiers[0].max.__str__() == "500"
    assert len(tariff.energy.periods[1].tiers) == 1
