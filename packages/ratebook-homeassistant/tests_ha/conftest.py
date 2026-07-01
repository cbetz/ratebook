"""Runtime Home Assistant test harness for the Ratebook integration.

Unlike tests/ (which never imports Home Assistant), this suite spins up a real HomeAssistant
instance via pytest-homeassistant-custom-component and drives the integration end to end.

Home Assistant discovers custom integrations by importing the top-level ``custom_components``
package (see homeassistant.loader._get_custom_components) and walking its ``__path__``. Putting
the package directory on sys.path makes ``custom_components.ratebook`` resolve, so the real
config flow, coordinator, and sensors run against the vendored engine.

The ``pytest_homeassistant_custom_component`` plugin is registered from the rootdir conftest.py
(pytest 8 requires ``pytest_plugins`` there), guarded so the no-HA suites still collect without
the ha-test dependency group.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# packages/ratebook-homeassistant/ — its custom_components/ratebook is a real package.
_HA_PKG = Path(__file__).resolve().parents[1]
if str(_HA_PKG) not in sys.path:
    sys.path.insert(0, str(_HA_PKG))


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load integrations from custom_components/ in every test."""
