"""Cross-engine charge-window vectors: the engine must reproduce v0_charge_windows.json.

Both the Python engine and the TypeScript port (charge_vectors.test.ts) read the SAME file;
regenerate it with `uv run python packages/ratebook/tests/generate_charge_vectors.py`.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from ratebook import BillingWindow, Tariff, cheapest_charge_window

VECTORS = json.loads((Path(__file__).parent / "vectors" / "v0_charge_windows.json").read_text())


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[c["name"] for c in VECTORS["cases"]])
def test_charge_window_vector(case: dict) -> None:
    tariff = Tariff.from_json(case["tariff"])
    window = BillingWindow(date.fromisoformat(case["window"]["start"]), case["window"]["days"])
    cw = cheapest_charge_window(tariff, window, case["charge_hours"], tier=case["tier"])
    assert cw.to_json() == case["expected"]
