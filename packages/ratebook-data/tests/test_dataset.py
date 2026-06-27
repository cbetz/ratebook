"""Dataset integrity: every curated tariff must load and be fully engine-supported.

Guards the published v0 dataset (`packages/ratebook-data/dataset/`) — if a tariff JSON or the
manifest drifts into a state the engine can't price, CI fails rather than shipping a broken record.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ratebook import Tariff, supported

DATASET = Path(__file__).resolve().parents[1] / "dataset"
MANIFEST = json.loads((DATASET / "manifest.json").read_text())
SLUGS = [t["slug"] for t in MANIFEST["tariffs"]]


def test_manifest_matches_files() -> None:
    on_disk = {p.stem for p in (DATASET / "tariffs").glob("*.json")}
    assert on_disk == set(SLUGS), "manifest and dataset/tariffs/ are out of sync"
    assert MANIFEST["count"] == len(SLUGS)


@pytest.mark.parametrize("slug", SLUGS)
def test_dataset_tariff_loads_and_is_supported(slug: str) -> None:
    tariff = Tariff.from_json(json.loads((DATASET / "tariffs" / f"{slug}.json").read_text()))
    assert supported(tariff).fully_supported, f"{slug} is not fully supported by the engine"


def test_confidence_values_are_valid() -> None:
    assert all(t["confidence"] in ("high", "medium", "low") for t in MANIFEST["tariffs"])
