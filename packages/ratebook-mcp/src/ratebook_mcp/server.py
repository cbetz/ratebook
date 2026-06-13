"""Ratebook MCP server — exposes the tariff database and rate engine to agents.

Four tools over the corpus + engine: lookup_tariff, estimate_bill, compare_plans,
best_charge_window. Run with ``ratebook-mcp`` (stdio transport) from a directory containing
``data/ratebook.duckdb`` (or set ``RATEBOOK_DB``). The actual logic lives in
:mod:`ratebook_mcp.service`; this module is the thin FastMCP binding.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import service

mcp = FastMCP("ratebook")


@mcp.tool()
def lookup_tariff(
    query: str, sector: str = "residential", active_only: bool = True, limit: int = 10
) -> dict[str, Any]:
    """Find electricity tariffs by utility name, EIA id, or exact URDB label.

    Returns matches freshest-first with provenance (source URL, effective date, last update)
    and whether the rate engine can fully price each plan. Use the returned `label` with the
    other tools.
    """
    return service.lookup_tariff(query, sector=sector, active_only=active_only, limit=limit)


@mcp.tool()
def estimate_bill(
    label: str,
    start_date: str,
    days: int,
    total_kwh: float | None = None,
    hourly_kwh: list[float] | None = None,
) -> dict[str, Any]:
    """Estimate the bill for a tariff (by `label`) over a billing window.

    `start_date` is ISO (YYYY-MM-DD); `days` is the billing-period length. Provide either
    `total_kwh` (a single number — sufficient for flat/tiered/seasonal plans) or `hourly_kwh`
    (a list of length days*24 — required for time-of-use plans). Returns the full result,
    including a typed `refusal` when the plan can't be priced from the given usage.
    """
    return service.estimate_bill_for(
        label, start_date=start_date, days=days, total_kwh=total_kwh, hourly_kwh=hourly_kwh
    )


@mcp.tool()
def compare_plans(
    labels: list[str],
    start_date: str,
    days: int,
    total_kwh: float | None = None,
    hourly_kwh: list[float] | None = None,
) -> dict[str, Any]:
    """Price several tariffs over the same usage and rank them cheapest-first.

    Returns `cheapest` (the winning label) and a sorted `comparison`. Plans that can't be
    priced from the given usage (e.g. time-of-use plans need `hourly_kwh`) are listed with
    their refusal reason rather than dropped.
    """
    return service.compare_plans(
        labels, start_date=start_date, days=days, total_kwh=total_kwh, hourly_kwh=hourly_kwh
    )


@mcp.tool()
def best_charge_window(
    label: str, start_date: str, days: int, charge_hours: int, kwh_to_add: float
) -> dict[str, Any]:
    """Find the cheapest contiguous time block to charge (e.g. an EV) on a tariff.

    Returns the cheapest `charge_hours`-long window within the period, its average marginal
    $/kWh, and the estimated energy cost to add `kwh_to_add` kWh. Uses the tariff's
    time-of-use price signal (energy only; demand charges not modeled in v0).
    """
    return service.best_charge_window(
        label, start_date=start_date, days=days, charge_hours=charge_hours, kwh_to_add=kwh_to_add
    )


def main() -> None:
    """Console entry point — runs the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
