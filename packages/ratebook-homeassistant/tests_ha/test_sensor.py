"""Runtime sensor tests: set up the integration and assert on the live entity states."""

from __future__ import annotations

from datetime import datetime

from custom_components.ratebook.const import (
    CONF_CHARGE_HOURS,
    CONF_CURRENCY,
    CONF_TARIFF_SOURCE,
    CONF_TIER,
    DOMAIN,
)
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

# pge-e-1 is a tiered (non-TOU) plan: tier 2 is a flat 0.40702 $/kWh every hour, so the price
# sensor is deterministic regardless of the frozen hour.
PGE_TIER2_PRICE = 0.40702
FROZEN = datetime(2025, 6, 2, 10, 30)  # a Monday, 10:30 UTC


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Ratebook (PG&E — E-1 Tiered (CA))",
        data={
            CONF_TARIFF_SOURCE: "pge-e-1",
            CONF_TIER: "2",
            CONF_CHARGE_HOURS: 4,
            CONF_CURRENCY: "USD",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@freeze_time(FROZEN)
async def test_price_sensor(hass: HomeAssistant) -> None:
    await _setup(hass)

    state = hass.states.get("sensor.ratebook_electricity_price")
    assert state is not None
    assert float(state.state) == PGE_TIER2_PRICE
    assert state.attributes["unit_of_measurement"] == "USD/kWh"

    raw_today = state.attributes["raw_today"]
    assert len(raw_today) == 24
    assert set(raw_today[0]) == {"start", "end", "value"}
    assert state.attributes["tomorrow_valid"] is True
    assert state.attributes["tier"] == 2
    assert state.attributes["currency"] == "USD"


@freeze_time(FROZEN)
async def test_charge_window_sensor(hass: HomeAssistant) -> None:
    await _setup(hass)

    state = hass.states.get("sensor.ratebook_cheapest_charge_window")
    assert state is not None
    # TIMESTAMP device class: the state parses as a datetime, and it is upcoming (>= now).
    start = dt_util.parse_datetime(state.state)
    assert start is not None
    assert start >= dt_util.now()

    assert state.attributes["hours"] == 4
    assert state.attributes["avg_rate"] == PGE_TIER2_PRICE
    assert state.attributes["end"] is not None
