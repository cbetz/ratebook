"""MCP service tests — gated on the corpus DB being built.

Run `uv run ratebook-data urdb` first; otherwise these skip.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from ratebook_mcp import service

DB = Path("data/ratebook.duckdb")
pytestmark = pytest.mark.skipif(
    not DB.exists(), reason="corpus DB not built (run: uv run ratebook-data urdb)"
)

PECO_RATE_R = "69e65026bc32447e430e25a9"  # default Rate R
SRP_E23 = "69a1b8bf40140c3bb007f1bd"
EVERSOURCE = "6969340fd06d027d0c0c65bc"


def test_lookup_returns_matches_with_provenance() -> None:
    out = service.lookup_tariff("PECO", limit=5)
    assert out["count"] >= 1
    first = out["results"][0]
    assert "PECO" in first["utility"]
    assert first["source_url"] and first["source_url"].startswith("http")
    assert "supported" in first and "structure" in first


def test_estimate_bill_matches_known_total() -> None:
    out = service.estimate_bill_for(PECO_RATE_R, start_date="2026-01-01", days=30, total_kwh=600)
    assert out["ok"]
    # 600 * 0.21884 (URDB bundled rate) + 11.30 (compare by value — JSON is canonical Decimal)
    assert Decimal(out["total"]) == Decimal("600") * Decimal("0.21884") + Decimal("11.30")
    assert out["tariff"]["label"] == PECO_RATE_R


def test_compare_plans_ranks_cheapest_first() -> None:
    out = service.compare_plans(
        [PECO_RATE_R, SRP_E23, EVERSOURCE], start_date="2026-06-01", days=30, total_kwh=700
    )
    assert out["cheapest"] == SRP_E23  # SRP E-23 is the cheapest of the three at 700 kWh
    totals = [Decimal(i["total"]) for i in out["comparison"] if i.get("ok")]
    assert totals == sorted(totals)


def test_best_charge_window_returns_window_and_cost() -> None:
    out = service.best_charge_window(
        SRP_E23, start_date="2026-06-01", days=1, charge_hours=4, kwh_to_add=40
    )
    assert out["hours"] == 4
    assert Decimal(out["estimated_energy_cost"]) > 0
    assert "start" in out and out["kwh_to_add"] == "40"
