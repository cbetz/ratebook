"""Structure + syntax validation for the HA integration (no Home Assistant install needed).

The pricing logic is tested in test_pricing.py; this guards the integration shell: the manifest
has the keys HA requires, the JSON files are well-formed and consistent, and every module is
syntactically valid (py_compile compiles without executing the `homeassistant` imports).
"""

from __future__ import annotations

import json
import py_compile
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "ratebook"


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
    assert any(r.startswith("ratebook-ha") for r in m["requirements"])


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
