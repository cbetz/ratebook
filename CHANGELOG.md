# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Until the first tagged release, everything lives under **Unreleased**. The engines are
versioned together: the Python engine and the TypeScript port must always reproduce the same
JSON test vectors, so a change to one is a change to both.

## [Unreleased]

## [0.2.0] - 2026-07-01

### Added

- **HA bundle: 15 → 30 audited plans.** Every bundled tariff was audited against the
  utility's CURRENT rate sheet (July 1, 2026) by an adversarial research workflow — only 3 of
  28 were fully accurate; the rest had drifted rates, stale adjustors, missing riders, or
  structural gaps, all now corrected with per-file `source_documents` + `last_verified`.
  Additions: the TOU companion for nearly every bundled utility (Con Edison SC-1 Rate III,
  Dominion 1T, DTE D1.2, Eversource Rate 7, FPL RTR-1, Georgia Power TOU-OA-14, PSE&G
  RS-TOU-3P, SRP E-26), the default CA TOU plans (PG&E E-TOU-C, SCE TOU-D-4-9PM), PECO Rate R
  + Rate R TOU, and — new to the dataset — the big-three **EV plans** (PG&E EV2-A, SCE
  TOU-D-PRIME, SDG&E EV-TOU-5), hand-authored from current rate sheets and independently
  re-derived by verifier agents. Notable corrections: Eversource CT Rate 1 was delivery-only
  ($0.163 → $0.236/kWh all-in), SDG&E TOU-DR1 got the May 2026 year-round super-off-peak
  window + AB 205 Base Services Charge, Con Edison Rate III gained its defining summer
  super-peak period ($1.18/kWh weekday afternoons), and National Grid MA R-4 turned out to be
  discontinued (kept in the dataset as history, excluded from the bundle).

- **Holiday-aware pricing** in both engines (Python + TypeScript, held together by new shared
  vectors `v0_holidays.json`): `Schedule` gains `holidays` (a closed vocabulary of 12 named US
  holidays, computed per-year — fixed dates + floating rules) and `holiday_observance`
  (`sunday_to_monday` — the prevailing utility rule — or `actual_day`). With
  `holiday_policy: "as_weekend"`, enumerated holidays price on the weekend schedule; an empty
  list is inert and surfaces a `holidays_not_enumerated` warning (replacing
  `holiday_policy_ignored_in_v0`).
- **Home Assistant — tier selection**: tiered plans (PG&E E-1/E-TOU-C, SCE, ConEd…) now price
  at the usage tier you pick in the config flow (baseline vs above-baseline differs ~20-25%
  on some plans); the active tier is a sensor attribute.
- **Home Assistant — Nordpool-compatible attributes**: `raw_today` / `raw_tomorrow`
  (`[{start, end, value}]`) plus `tomorrow_valid: true`, so existing cheapest-hours
  automations, blueprints, and ApexCharts configs work as a drop-in swap; also
  `today_is_holiday` / `tomorrow_is_holiday`.
- **Home Assistant — config-flow UX**: the tariff dropdown shows human labels
  ("PG&E — E-1 Tiered (CA)") from a generated `tariffs/index.json`
  (`scripts/sync_bundled_tariffs.py` + `scripts/bundle.json`); custom tariff JSON gets a
  multiline field.
- **Docs**: Energy Dashboard setup guide (the price entity is designed for "Use an entity
  with the current price"), tariff authoring guide (`docs/AUTHORING_TARIFFS.md`), a
  request-a-utility issue template, and an honest comparison vs ha-openei / MIDAS / ComEd /
  Emporia in the distribution README.

### Fixed

- **Vendored-import bug that broke real installs** (caught by adversarial review): the
  adapter's new `from ratebook.schema import …` was not rewritten by `sync_vendor.py`, so
  the shipped integration raised `ModuleNotFoundError` outside the monorepo — and inside it,
  silently bound the workspace enum, breaking holiday day-typing. The rewriter now handles
  every `from ratebook…` form, and a subprocess test imports the vendored tree with the
  workspace package blocked.
- `raw_today` / `raw_tomorrow` timestamps are timezone-aware (Nordpool consumers compare
  them against `now()`); the bulky schedule attributes are excluded from the recorder
  (`_unrecorded_attributes`) so history stays lean.
- Negative tier indexes clamp to tier 1 in both engines instead of silently pricing at the
  top tier (Python) or throwing (TypeScript); TypeScript now rejects unknown holiday names
  at parse time, matching Python.
- Post-audit data corrections from an independent verification pass: PSE&G RS gains the ZEC
  Return-of-Excess-Collections credit (−$0.004265/kWh), both Con Edison SC-1 entries gain
  the GR 26 RDM + CESD adders (+$0.007581/kWh), and SCE Domestic D's unverifiable $0.00842
  adj was zeroed to match SCE's published 30¢/40¢ tier prices.

## [0.1.0] - 2026-06-27

### Added

- **v0 tariff dataset** (`packages/ratebook-data/dataset/`): 65 engine-validated US residential
  tariffs across 37 utilities and 26 states + DC (all rate structures), URDB-derived and CC0, with
  provenance and a confidence flag per record. 15 recognizable plans are bundled into the Home
  Assistant integration as selectable options ("pick your utility").
- **Charge-window optimization in the TypeScript engine** (`cheapestChargeWindow`,
  `hourlyMarginalPrices`), held to the Python engine by shared vectors
  (`v0_charge_windows.json`) — and forward-looking (a `not_before` cutoff so it never returns a
  past window).
- **Rate engine** (`packages/ratebook`): deterministic, pure-function engine that prices US
  electricity tariffs from a typed schema. `Decimal` end to end, JSON-as-strings for exact
  cross-language arithmetic. One accounting abstraction (`BillingWindow`); day count is a
  required explicit input, never inferred. Refusal is a typed return value (`BillResult.ok =
  False`), never a partial number — "unknown" is a first-class answer. Frozen dataclasses,
  zero runtime dependencies, hand-written JSON round-trip.
- **Shared test vectors** (`packages/ratebook/tests/vectors/v0_bills.json`): the cross-engine
  contract. Regenerated via `uv run python packages/ratebook/tests/generate_vectors.py`.
- **Data plant** (`packages/ratebook-data`): ingestion and extraction pipeline. `uv run
  ratebook-data urdb` downloads the URDB bulk CSV into `data/raw/` and loads it into a DuckDB
  corpus, recording the source URL and SHA-256. Includes golden-set and bill-match tests, plus
  PySAM cross-validation.
- **MCP server** (`packages/ratebook-mcp`): stdio MCP server (`uv run ratebook-mcp`) exposing
  four tools over the corpus and engine — `lookup_tariff`, `estimate_bill`, `compare_plans`,
  and `best_charge_window`.
- **TypeScript engine port** (`packages/ratebook-ts`, `@ratebook/engine`): port of the rate
  engine held to the Python engine via the shared JSON test vectors. Tested with vitest
  (`pnpm -C packages/ratebook-ts test`).
- **Home Assistant integration** (`packages/ratebook-homeassistant`): custom integration with a
  config flow and two sensors over the engine — current marginal electricity price (with the
  day's schedule as attributes, including an evcc-shaped forecast) and the start time of the
  cheapest contiguous charge window over the next 24 hours. The engine + adapter are vendored
  under `custom_components/ratebook/vendor/` (generated by `scripts/sync_vendor.py`, sync-checked
  in CI), so the integration is copy-installable with **no PyPI or network dependency**. Includes
  a reconfigure flow (switch tariff/charge-window/currency in place) and distributed as a HACS
  mirror at [cbetz/ratebook-homeassistant](https://github.com/cbetz/ratebook-homeassistant).

### Notes

- Pre-release. Schema, APIs, and the corpus may change without notice until a tagged release.
- The published datasets are dedicated to the public domain under CC0-1.0; the seed corpus
  derives from the CC0 U.S. Utility Rate Database (URDB).

[Unreleased]: https://github.com/cbetz/ratebook/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/cbetz/ratebook/releases/tag/v0.1.0
