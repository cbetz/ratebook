"""Regenerate the cross-engine charge-window vectors.

Run: ``uv run python packages/ratebook/tests/generate_charge_vectors.py``

Writes ``tests/vectors/v0_charge_windows.json`` — the language-agnostic oracle that BOTH the
Python engine (``test_charge_vectors.py``) and the TypeScript port (``charge_vectors.test.ts``)
must reproduce byte-for-byte for ``cheapest_charge_window``. Cases are chosen so the block's
average rate divides EXACTLY (flat → the rate itself; the 0.10/0.30 TOU at 4/8h → multiples of
0.025), so the expected ``avg_rate`` is independent of each engine's Decimal context precision.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conftest import peco_rate_r, seasonal_tariff, tiered_tariff, tou_tariff
from ratebook import BillingWindow, cheapest_charge_window

MONDAY = date(2025, 6, 2)  # a Monday → weekday TOU schedule applies


def _case(name, tariff, start, days, charge_hours, tier=0):
    window = BillingWindow(start, days)
    cw = cheapest_charge_window(tariff, window, charge_hours, tier=tier)
    return {
        "name": name,
        "tariff": tariff.to_json(),
        "window": {"start": start.isoformat(), "days": days},
        "charge_hours": charge_hours,
        "tier": tier,
        "expected": cw.to_json(),
    }


def build() -> dict:
    return {
        "cases": [
            _case("flat 4h (avg = the flat rate)", peco_rate_r(), MONDAY, 1, 4),
            _case("tou 4h avoids peak (all off-peak)", tou_tariff(), MONDAY, 1, 4),
            _case("tou 8h all off-peak", tou_tariff(), MONDAY, 1, 8),
            _case("tou 4h over a 2-day window", tou_tariff(), MONDAY, 2, 4),
            _case("seasonal 6h (single season → flat rate)", seasonal_tariff(), MONDAY, 1, 6),
            _case("tiered 5h marginal at tier 0", tiered_tariff(), MONDAY, 1, 5),
        ]
    }


if __name__ == "__main__":
    out = Path(__file__).parent / "vectors" / "v0_charge_windows.json"
    out.write_text(json.dumps(build(), indent=2) + "\n")
    print(f"wrote {out}")
