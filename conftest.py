"""Workspace-root pytest config.

The runtime Home Assistant suite (packages/ratebook-homeassistant/tests_ha/) only works when
the ``ha-test`` dependency group is installed. pytest 8 requires ``pytest_plugins`` to live in
the rootdir conftest, so the HA test plugin is registered here — but only when it is importable,
so a plain ``uv run pytest`` (no group) still collects the other suites. When it is absent, the
runtime suite is skipped entirely. Run it with:

    uv run --group ha-test pytest packages/ratebook-homeassistant/tests_ha/
"""

from __future__ import annotations

import importlib.util

collect_ignore_glob: list[str] = []
if importlib.util.find_spec("pytest_homeassistant_custom_component") is not None:
    pytest_plugins = ["pytest_homeassistant_custom_component"]
else:
    collect_ignore_glob.append("packages/ratebook-homeassistant/tests_ha/*")
