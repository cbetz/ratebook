# Ratebook for Home Assistant

A Home Assistant custom integration that turns a Ratebook tariff into live electricity-price
sensors and a cheapest-charge-window sensor — the price signal that EV chargers, evcc, EMHASS,
and HA automations need to answer "what does a kWh cost right now, and when should I charge?"

It is a thin shell over the deterministic [`ratebook`](../ratebook) rate engine. The price math
lives in the `ratebook_ha` package (unit-tested without Home Assistant); `custom_components/ratebook`
is the HA binding (config flow, coordinator, sensors).

## Entities

- **`sensor.ratebook_electricity_price`** — the current marginal price ($/kWh). Attributes
  `today` / `tomorrow` carry the full hourly price schedule (`{start, price}` per hour), the
  shape evcc and price-aware automations consume.
- **`sensor.ratebook_cheapest_charge_window`** — the start time of the cheapest contiguous
  charge block in the next 24 hours (timestamp). Attributes: `end`, `avg_rate`, `hours`.

## Configuration

Add via Settings → Devices & Services → Add Integration → Ratebook. Pick a bundled example
tariff (a generic time-of-use or flat residential plan) or paste a Ratebook tariff JSON, then
set the charge-window length (hours) and currency.

## Install

The integration is self-contained: the `ratebook` engine and `ratebook_ha` adapter are vendored
under `custom_components/ratebook/vendor/`, so it has **no PyPI or network dependencies**.

**Manual copy (works today):** copy the `custom_components/ratebook` directory into your Home
Assistant `config/custom_components/` directory, restart Home Assistant, then add the integration
via Settings → Devices & Services → Add Integration → Ratebook.

**HACS:** custom-repository install is pending a layout change — HACS expects `custom_components/`
at a repository root, and this integration currently lives in a monorepo subdirectory (tracked in
`docs/ROADMAP.md`).

> Status: v0. Prices are the tariff's energy marginal price (time-of-use signal); demand
> charges and tier-vs-baseline position are not modeled — see the engine docs.
