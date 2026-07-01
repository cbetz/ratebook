"""Runtime setup/unload round-trip for the Ratebook config entry."""

from __future__ import annotations

from custom_components.ratebook.const import (
    CONF_CHARGE_HOURS,
    CONF_CURRENCY,
    CONF_TARIFF_SOURCE,
    CONF_TIER,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TARIFF_SOURCE: "pge-e-1",
            CONF_TIER: "1",
            CONF_CHARGE_HOURS: 4,
            CONF_CURRENCY: "USD",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not None
    assert hass.states.get("sensor.ratebook_electricity_price") is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
