"""Runtime config-flow tests: the real flow handler creating and reconfiguring entries."""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.ratebook.const import (
    CONF_CHARGE_HOURS,
    CONF_CURRENCY,
    CONF_TARIFF_JSON,
    CONF_TARIFF_SOURCE,
    CONF_TIER,
    CUSTOM,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

# A bundled tariff's raw JSON, reused for the custom-tariff path.
_TARIFFS = Path(__file__).resolve().parents[1] / "src" / "ratebook_ha" / "tariffs"


async def test_user_flow_with_bundled_tariff(hass: HomeAssistant) -> None:
    """Picking a bundled slug creates an entry titled with the utility label."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TARIFF_SOURCE: "pge-e-1",
            CONF_TIER: "2",
            CONF_CHARGE_HOURS: 4,
            CONF_CURRENCY: "USD",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "PG&E" in result["title"]
    assert result["data"][CONF_TARIFF_SOURCE] == "pge-e-1"
    assert result["data"][CONF_TIER] == "2"


async def test_user_flow_custom_json_invalid_then_valid(hass: HomeAssistant) -> None:
    """Invalid custom JSON shows invalid_tariff; a real tariff JSON then creates the entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TARIFF_SOURCE: CUSTOM,
            CONF_TARIFF_JSON: "not valid json {",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_tariff"}

    tariff_text = (_TARIFFS / "flat-residential.json").read_text()
    # Sanity: it really is a loadable tariff, not just any JSON.
    json.loads(tariff_text)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TARIFF_SOURCE: CUSTOM,
            CONF_TARIFF_JSON: tariff_text,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Ratebook (Custom tariff)"
    assert result["data"][CONF_TARIFF_JSON] == tariff_text


async def test_reconfigure_updates_entry_in_place(hass: HomeAssistant) -> None:
    """Reconfigure edits the existing entry (title changes, no second entry appears)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Ratebook (PG&E — E-1 Tiered (CA))",
        data={
            CONF_TARIFF_SOURCE: "pge-e-1",
            CONF_TIER: "1",
            CONF_CHARGE_HOURS: 4,
            CONF_CURRENCY: "USD",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_TARIFF_SOURCE: "flat-residential",
            CONF_TIER: "1",
            CONF_CHARGE_HOURS: 6,
            CONF_CURRENCY: "USD",
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1  # updated in place, not duplicated
    assert entries[0].data[CONF_TARIFF_SOURCE] == "flat-residential"
    assert entries[0].data[CONF_CHARGE_HOURS] == 6
    assert "PG&E" not in entries[0].title
