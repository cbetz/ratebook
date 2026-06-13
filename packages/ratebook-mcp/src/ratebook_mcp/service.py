"""Service layer behind the MCP tools — plain functions returning JSON-ready dicts.

Kept separate from the FastMCP wiring so the logic is unit-testable without a running server.
Each function loads tariffs from the DuckDB corpus (``ratebook_data.corpus``) and prices them
with the engine (``ratebook``). All Decimals are serialized to strings (the engine's canonical
wire form), so every return value is directly JSON-serializable.
"""

from __future__ import annotations

import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from ratebook import (
    BillingWindow,
    Usage,
    cheapest_charge_window,
    estimate_bill,
    supported,
)
from ratebook_data.corpus import load_tariff, search_tariffs

#: Corpus DB location; override with RATEBOOK_DB for a non-default deployment.
DB_PATH = Path(os.environ.get("RATEBOOK_DB", "data/ratebook.duckdb"))

_SECTOR_DB = {
    "residential": "Residential",
    "commercial": "Commercial",
    "industrial": "Industrial",
    "lighting": "Lighting",
}


def _first_url(source: str | None) -> str | None:
    for part in re.split(r"[\r\n]+", source or ""):
        part = part.strip()
        if part.startswith("http"):
            return part
    return None


def _usage(total_kwh: float | None, hourly_kwh: list[float] | None) -> Usage:
    if hourly_kwh is not None:
        return Usage.hourly(hourly_kwh)
    if total_kwh is not None:
        return Usage.aggregate(total_kwh)
    raise ValueError("provide either total_kwh or hourly_kwh")


def lookup_tariff(
    query: str,
    *,
    sector: str | None = "residential",
    active_only: bool = True,
    limit: int = 10,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Find tariffs by utility name, EIA id, or exact label, freshest first, with provenance
    and whether the v0 engine can price each."""
    sector_db = _SECTOR_DB.get(sector.lower()) if sector else None
    rows = search_tariffs(
        query, db_path=db_path, sector=sector_db, active_only=active_only, limit=limit
    )
    results: list[dict[str, Any]] = []
    for r in rows:
        entry: dict[str, Any] = {
            "label": r["label"],
            "utility": r["utility"],
            "eiaid": r["eiaid"],
            "plan_name": r["name"],
            "sector": r["sector"],
            "effective_start": (r["startdate"] or "")[:10] or None,
            "latest_update": (r["latest_update"] or "")[:10] or None,
            "source_url": _first_url(r["source"]),
        }
        try:
            tariff = load_tariff(r["label"], db_path)
            report = supported(tariff)
            entry["supported"] = report.fully_supported
            if not report.fully_supported:
                entry["unsupported_reasons"] = list(report.reasons)
            entry["structure"] = {
                "periods": len(tariff.energy.periods),
                "max_tiers": max(len(p.tiers) for p in tariff.energy.periods),
            }
        except Exception as exc:  # malformed records are quarantined, not crashes
            entry["supported"] = False
            entry["import_error"] = str(exc)[:120]
        results.append(entry)
    return {"query": query, "count": len(results), "results": results}


def estimate_bill_for(
    label: str,
    *,
    start_date: str,
    days: int,
    total_kwh: float | None = None,
    hourly_kwh: list[float] | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Estimate a bill for one tariff over a billing window. Returns the engine's full
    BillResult (``ok``/``total``/``energy_charge``/``fixed_charge``/``refusal``/``warnings``)."""
    tariff = load_tariff(label, db_path)
    window = BillingWindow(date.fromisoformat(start_date), days)
    result = estimate_bill(tariff, _usage(total_kwh, hourly_kwh), window)
    out = result.to_json()
    out["tariff"] = {
        "label": label,
        "utility": tariff.identity.utility_id,
        "plan_name": tariff.identity.plan_name,
    }
    return out


def compare_plans(
    labels: list[str],
    *,
    start_date: str,
    days: int,
    total_kwh: float | None = None,
    hourly_kwh: list[float] | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Price several tariffs over the same usage/window and rank cheapest-first. Plans the
    engine can't price from the given usage (e.g. TOU needs hourly load) are listed with their
    refusal rather than dropped."""
    window = BillingWindow(date.fromisoformat(start_date), days)
    usage = _usage(total_kwh, hourly_kwh)
    items: list[dict[str, Any]] = []
    for label in labels:
        try:
            tariff = load_tariff(label, db_path)
            result = estimate_bill(tariff, usage, window)
            items.append(
                {
                    "label": label,
                    "plan_name": tariff.identity.plan_name,
                    "utility": tariff.identity.utility_id,
                    "ok": result.ok,
                    "total": str(result.total) if result.ok else None,
                    "refusal": result.refusal.reason.value if result.refusal else None,
                }
            )
        except Exception as exc:
            items.append({"label": label, "ok": False, "error": str(exc)[:120]})

    def _key(item: dict[str, Any]) -> tuple[bool, Decimal]:
        return (
            not item.get("ok"),
            Decimal(item["total"]) if item.get("total") else Decimal("Infinity"),
        )

    items.sort(key=_key)
    cheapest = next((i["label"] for i in items if i.get("ok")), None)
    return {"cheapest": cheapest, "comparison": items}


def best_charge_window(
    label: str,
    *,
    start_date: str,
    days: int,
    charge_hours: int,
    kwh_to_add: float,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Find the cheapest contiguous ``charge_hours``-long block to add ``kwh_to_add`` kWh of
    load (e.g. EV charging) on a tariff, using its time-of-use marginal price signal."""
    tariff = load_tariff(label, db_path)
    window = BillingWindow(date.fromisoformat(start_date), days)
    cw = cheapest_charge_window(tariff, window, charge_hours)
    out = cw.to_json()
    out["kwh_to_add"] = str(kwh_to_add)
    out["estimated_energy_cost"] = str(Decimal(str(kwh_to_add)) * cw.avg_rate)
    out["tariff"] = {"label": label, "plan_name": tariff.identity.plan_name}
    out["note"] = (
        "Marginal energy price signal only (time-of-use). Demand charges and tier position "
        "relative to baseline usage are not modeled in v0."
    )
    return out
