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

import re
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

    # The adapter imports the engine by its absolute name; rewrite EVERY such import to a
    # relative one so it resolves to the sibling vendored engine, not a global `ratebook`.
    # (`from ratebook import X`, `from ratebook.schema import Y`, … — a missed form means
    # ModuleNotFoundError on a real install, where no top-level `ratebook` exists.)
    import_re = re.compile(r"^(\s*)from ratebook(\.[\w.]+)? import ", flags=re.MULTILINE)
    rewritten_any = False
    for module in (dest / "ratebook_ha").rglob("*.py"):
        text = module.read_text()
        new_text, n = import_re.subn(r"\1from ..ratebook\2 import ", text)
        if n:
            rewritten_any = True
            module.write_text(new_text)
        if re.search(r"^\s*import ratebook\b", new_text, flags=re.MULTILINE):
            raise SystemExit(f"unrewritable 'import ratebook' in {module} — vendor aborted")
    if not rewritten_any:
        raise SystemExit("expected engine imports in the adapter — vendor aborted")


if __name__ == "__main__":
    build_vendor(VENDOR)
    print(f"vendored engine + adapter into {VENDOR.relative_to(REPO)}")
