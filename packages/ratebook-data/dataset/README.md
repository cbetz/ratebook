# Ratebook v0 tariff dataset

A curated, **engine-validated** set of US residential electricity tariffs — one or two plans
(a standard default plan, usually plus a time-of-use companion) for major utilities across the
country, plus the big-three California EV plans. Every tariff here is fully priceable by the
[Ratebook engine](../../ratebook) (validated with `supported()`), so an app/device/agent can
compute a bill or a cheapest-charge-window from it directly.

- **Coverage:** 68 tariffs, ~38 utilities across 26 states + DC; all five rate structures
  (tiered, time-of-use, seasonal, flat, TOU-tiered) plus EV plans (PG&E EV2-A, SCE
  TOU-D-PRIME, SDG&E EV-TOU-5). See `manifest.json`.
- **Provenance:** seeded from the [U.S. Utility Rate Database](https://apps.openei.org/USURDB/)
  (URDB) snapshot `usurdb-2026-06-13`; the EV plans are hand-authored from current rate
  sheets. Each entry carries a `source_url`, a `confidence` (high/medium/low), and a `note`;
  URDB-derived entries keep their URDB `label`. **The 30 plans shipped in the Home Assistant
  bundle were audited against each utility's current rate sheet on 2026-07-01** — those files
  carry `source_documents` + `provenance.last_verified`, corrected all-in rates
  (supply + delivery + riders), and their rate sheet's holiday rules. Un-audited entries are
  URDB-as-of-snapshot: they can be stale or carry a component-only rate — verify against your
  bill. Fresh PDF extraction (the eval'd, distribution-aware path) is tracked in
  `docs/GOLDEN_SET.md` and grows via tariff corrections.
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
covered by a single utility. One entry (National Grid MA R-4) is retained for history but
**discontinued by the utility** and excluded from the Home Assistant bundle, as are the
remaining low/medium-confidence un-audited entries. Want your utility in?
[Request it](https://github.com/cbetz/ratebook/issues/new?template=request-a-utility.yml) or
see [`docs/AUTHORING_TARIFFS.md`](../../../docs/AUTHORING_TARIFFS.md) — contributions and
corrections welcome (`CONTRIBUTING.md`).
