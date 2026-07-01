"""Structure + syntax validation for the HA integration (no Home Assistant install needed).

The pricing logic is tested in test_pricing.py; this guards the integration shell: the manifest
has the keys HA requires, the JSON files are well-formed and consistent, every module is
syntactically valid (py_compile compiles without executing the `homeassistant` imports), and the
vendored engine/adapter is in sync with the workspace source AND importable with no external deps.
"""

from __future__ import annotations

import importlib.util
import json
import py_compile
import sys
from datetime import datetime
from pathlib import Path

import pytest

HA_PKG = Path(__file__).resolve().parents[1]
INTEGRATION = HA_PKG / "custom_components" / "ratebook"
VENDOR = INTEGRATION / "vendor"


def _json(name: str) -> dict:
    return json.loads((INTEGRATION / name).read_text())


def test_manifest_has_required_keys() -> None:
    m = _json("manifest.json")
    for key in (
        "domain",
        "name",
        "version",
        "config_flow",
        "requirements",
        "iot_class",
        "documentation",
        "codeowners",
    ):
        assert key in m, f"manifest missing {key}"
    assert m["domain"] == "ratebook"
    assert m["config_flow"] is True
    # The engine + adapter are vendored under vendor/, so the integration has NO external
    # (pip/PyPI) requirements — it is copy-installable with zero network dependency.
    assert m["requirements"] == []


def test_const_domain_matches_manifest() -> None:
    const = (INTEGRATION / "const.py").read_text()
    assert 'DOMAIN: Final = "ratebook"' in const


def test_strings_and_translation_match() -> None:
    strings = _json("strings.json")
    en = _json("translations/en.json")
    assert strings == en
    assert "user" in strings["config"]["step"]
    # Entity translation keys must match the sensors' _attr_translation_key values.
    sensor_src = (INTEGRATION / "sensor.py").read_text()
    for key in strings["entity"]["sensor"]:
        assert f'_attr_translation_key = "{key}"' in sensor_src


@pytest.mark.parametrize(
    "module",
    ["__init__.py", "const.py", "coordinator.py", "config_flow.py", "sensor.py"],
)
def test_module_compiles(module: str) -> None:
    py_compile.compile(str(INTEGRATION / module), doraise=True)


# --------------------------------------------------------------------------------------
# Vendored dependencies (vendor/): must stay in sync with source AND import with no deps.
# --------------------------------------------------------------------------------------
def _tree(root: Path) -> dict[str, bytes]:
    """Relative-path -> bytes for every file under ``root``, ignoring bytecode caches."""
    out: dict[str, bytes] = {}
    for p in root.rglob("*"):
        if p.is_file() and "__pycache__" not in p.parts:
            out[str(p.relative_to(root))] = p.read_bytes()
    return out


def _load_sync_script():
    path = HA_PKG / "scripts" / "sync_vendor.py"
    spec = importlib.util.spec_from_file_location("ratebook_sync_vendor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_vendor_in_sync(tmp_path: Path) -> None:
    """The committed vendor/ tree must be exactly what sync_vendor.py regenerates from source."""
    _load_sync_script().build_vendor(tmp_path / "vendor")
    assert _tree(tmp_path / "vendor") == _tree(VENDOR), (
        "vendor/ is stale — run: python3 packages/ratebook-homeassistant/scripts/sync_vendor.py"
    )


def test_vendored_integration_imports_and_prices() -> None:
    """The vendored engine+adapter import and price a tariff with no external dependency."""
    sys.path.insert(0, str(INTEGRATION))
    try:
        from vendor.ratebook_ha import pricing  # type: ignore[import-not-found]

        names = pricing.list_bundled()
        assert names, "no bundled tariffs vendored"
        price = pricing.current_price(pricing.load_bundled(names[0]), datetime(2026, 6, 1, 18, 0))
        assert isinstance(price, float)
    finally:
        sys.path.remove(str(INTEGRATION))
        for name in [m for m in sys.modules if m == "vendor" or m.startswith("vendor.")]:
            del sys.modules[name]


def test_vendored_tree_survives_without_workspace_ratebook() -> None:
    """The vendor tree must work on a REAL install, where no top-level `ratebook` exists.

    In this repo the workspace `ratebook` package hides un-rewritten absolute imports (the
    vendored module silently binds the workspace copy — and its enums fail `is` checks
    against the vendored classes). Run in a subprocess with `ratebook` imports blocked, and
    assert holiday day-typing works end to end (the enum-identity failure mode).
    """
    code = f"""
import sys
sys.path.insert(0, {str(INTEGRATION)!r})
class _BlockWorkspaceRatebook:
    def find_spec(self, name, *args, **kwargs):
        if name == "ratebook" or name.startswith("ratebook."):
            raise ModuleNotFoundError(
                f"blocked: {{name}} — the vendored tree must not import the workspace package"
            )
sys.meta_path.insert(0, _BlockWorkspaceRatebook())
from vendor.ratebook_ha import pricing
import datetime as dt
# PECO Rate R TOU: weekday peak 2-6pm, Labor Day priced on the weekend schedule.
t = pricing.load_bundled("peco-rate-r-tou")
assert pricing.is_holiday(t, dt.date(2026, 9, 7)) is True, "Labor Day 2026 must be a holiday"
assert pricing.is_holiday(t, dt.date(2026, 9, 8)) is False
assert pricing.current_price(t, dt.datetime(2026, 9, 7, 15)) < pricing.current_price(
    t, dt.datetime(2026, 9, 8, 15)
), "holiday afternoon must price off-peak"
"""
    import subprocess

    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
