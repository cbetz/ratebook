#!/usr/bin/env python3
"""Vendor the pure-Python `ratebook` engine + `ratebook_ha` adapter into the HA integration.

Home Assistant pip-installs an integration's `manifest.json` requirements at load time. Rather
than depend on (as-yet unpublished) PyPI packages, we bundle the engine + adapter source into
`custom_components/ratebook/vendor/` so the integration is a self-contained, copy-installable
unit with zero network dependencies.

The vendored tree is GENERATED from the workspace source by this script — never edit it by hand.
`test_vendor.py` regenerates into a temp dir and asserts the committed copy is in sync, so drift
is caught in CI. Run after changing the engine or the adapter:

    python3 packages/ratebook-homeassistant/scripts/sync_vendor.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

# repo/packages/ratebook-homeassistant/scripts/sync_vendor.py -> repo
REPO = Path(__file__).resolve().parents[3]
ENGINE_SRC = REPO / "packages" / "ratebook" / "src" / "ratebook"
ADAPTER_SRC = REPO / "packages" / "ratebook-homeassistant" / "src" / "ratebook_ha"
VENDOR = REPO / "packages" / "ratebook-homeassistant" / "custom_components" / "ratebook" / "vendor"

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")

_HEADER = '''"""AUTO-GENERATED vendored dependencies — DO NOT EDIT.

Bundled copies of the `ratebook` engine and `ratebook_ha` adapter so the Home Assistant
integration installs with no PyPI/network dependency. Regenerate with
`python3 packages/ratebook-homeassistant/scripts/sync_vendor.py`; `test_vendor.py` enforces
that this tree stays byte-identical to the workspace source (modulo the import rewrite below).
"""
'''


def build_vendor(dest: Path) -> None:
    """Build the vendored tree into ``dest`` (idempotent: wipes and rewrites it)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "__init__.py").write_text(_HEADER)

    shutil.copytree(ENGINE_SRC, dest / "ratebook", ignore=_IGNORE)
    shutil.copytree(ADAPTER_SRC, dest / "ratebook_ha", ignore=_IGNORE)

    # The adapter is the only file with a cross-package absolute import; rewrite it to a
    # relative import so it resolves to the sibling vendored engine, not a global `ratebook`.
    pricing = dest / "ratebook_ha" / "pricing.py"
    text = pricing.read_text()
    rewritten = text.replace("from ratebook import (", "from ..ratebook import (")
    if rewritten == text:
        raise SystemExit("expected 'from ratebook import (' in adapter pricing.py — vendor aborted")
    pricing.write_text(rewritten)


if __name__ == "__main__":
    build_vendor(VENDOR)
    print(f"vendored engine + adapter into {VENDOR.relative_to(REPO)}")
