#!/usr/bin/env python3
"""Sync the HA integration's bundled tariffs from the ratebook-data dataset.

``bundle.json`` (next to this script) is the source of truth for WHICH dataset tariffs ship
in the Home Assistant "pick your utility" dropdown and what label each shows. This script
copies the tariff JSONs from ``packages/ratebook-data/dataset/tariffs/`` into
``src/ratebook_ha/tariffs/`` and regenerates ``tariffs/index.json`` (slug → dropdown label).

The two generic example tariffs (``generic-tou``, ``flat-residential``) live only in the
adapter package and are preserved as-is.

Run after editing bundle.json or the dataset, then re-vendor:

    python3 packages/ratebook-homeassistant/scripts/sync_bundled_tariffs.py
    python3 packages/ratebook-homeassistant/scripts/sync_vendor.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATASET = REPO / "packages" / "ratebook-data" / "dataset"
TARIFFS_DIR = REPO / "packages" / "ratebook-homeassistant" / "src" / "ratebook_ha" / "tariffs"
BUNDLE = Path(__file__).parent / "bundle.json"

#: Adapter-local example tariffs that are not part of the dataset.
GENERIC = {
    "generic-tou": "Generic — Time-of-Use example (peak 4-9pm)",
    "flat-residential": "Generic — Flat-rate example",
}


def main() -> int:
    bundle = json.loads(BUNDLE.read_text())
    manifest = {
        t["slug"]: t for t in json.loads((DATASET / "manifest.json").read_text())["tariffs"]
    }

    slugs = bundle["slugs"]
    overrides: dict[str, str] = bundle.get("labels", {})
    missing = [s for s in slugs if s not in manifest]
    if missing:
        print(f"ERROR: not in dataset manifest: {missing}")
        return 1

    # Wipe non-generic tariffs, then copy the bundle fresh so removals propagate.
    for p in TARIFFS_DIR.glob("*.json"):
        if p.stem not in GENERIC and p.name != "index.json":
            p.unlink()
    index: list[dict[str, str]] = []
    for slug in slugs:
        shutil.copy2(DATASET / "tariffs" / f"{slug}.json", TARIFFS_DIR / f"{slug}.json")
        m = manifest[slug]
        label = overrides.get(slug, f"{m['utility_display']} — {m['plan_name']} ({m['state']})")
        index.append({"slug": slug, "label": label})
    for slug, label in GENERIC.items():
        index.append({"slug": slug, "label": label})

    index.sort(key=lambda e: e["label"].lower())
    (TARIFFS_DIR / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"synced {len(slugs)} dataset tariffs + {len(GENERIC)} generics; index.json written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
