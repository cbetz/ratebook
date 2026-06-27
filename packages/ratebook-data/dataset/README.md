# Ratebook v0 tariff dataset

A curated, **engine-validated** set of US residential electricity tariffs — one or two plans
(a standard default plan, usually plus a time-of-use companion) for major utilities across the
country. Every tariff here is fully priceable by the [Ratebook engine](../../ratebook) (validated
with `supported()`), so an app/device/agent can compute a bill or a cheapest-charge-window from it
directly.

- **Coverage (v0):** ~37 utilities across 26 states + DC; all five rate structures (tiered,
  time-of-use, seasonal, flat, TOU-tiered). See `manifest.json`.
- **Provenance:** derived from the [U.S. Utility Rate Database](https://apps.openei.org/USURDB/)
  (URDB) snapshot `usurdb-2026-06-13`. Each entry carries its URDB `label`, a `source_url`, and a
  `confidence` (high/medium/low) with a `note`. **URDB is a starting point — it can be stale or
  carry a bundled rate; verify against your bill.** Fresh PDF extraction (the eval'd, distribution-
  aware path) is tracked in `docs/GOLDEN_SET.md` and grows via tariff corrections.
- **License:** the published dataset is dedicated to the public domain under
  [CC0-1.0](../../../LICENSE-DATA) (URDB is CC0).

## Layout
- `manifest.json` — one record per tariff: `slug`, `utility_display`, `state`, `plan_name`,
  `tariff_type`, `energy_rate`, `fixed_charge`, `label` (URDB), `source_url`, `confidence`, `note`.
- `tariffs/<slug>.json` — the canonical `Tariff` JSON (load with `ratebook.Tariff.from_json`).

## Use
```python
import json
from ratebook import Tariff, Usage, BillingWindow, estimate_bill
t = Tariff.from_json(json.loads(open("tariffs/pge-e-1.json").read()))
```

## Honest gaps (v0)
Coastal + Sun Belt skew; the deregulated Texas (ERCOT) retail market is largely absent; limited
Pacific-Northwest public power and some Southeast names (TVA, Duke Progress); many states are
covered by a single utility. Two entries (SMUD, Pepco DC RTM-TOU) are low-confidence and seven are
medium — flagged in the manifest and **excluded from the Home Assistant "pick your utility"
bundle**, which ships only high-confidence, recognizable plans. Contributions (tariff corrections)
welcome — see `CONTRIBUTING.md`.
