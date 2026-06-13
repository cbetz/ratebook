# Ratebook Engine + Schema v0 — Implementation Spec

Status: authoritative for Sprint 0 item 3. Synthesized from three competing designs
(`pysam-fidelity`, `bill-match-first`, `minimal-boring`) and two judge panels, then
reconciled by the implementer. Every load-bearing claim was checked against the corpus
(`data/ratebook.duckdb`, `raw.urdb`, snapshot 2026-06-12).

The governing rule, from `CLAUDE.md`: the rate engine is **pure functions, deterministic,
boring, and bulletproof** — a correctness bug here is a customer-facing "your app lied
about my bill" failure. **"Unknown" is a first-class answer:** the engine refuses
explicitly rather than ever returning a wrong number.

---

## 0. Decisions locked (and why)

1. **One accounting abstraction: the `BillingWindow`.** A window is a date span with an
   explicit integer `days` count; **tiers reset exactly once per window, and nothing else
   resets.** Bill-match = one window (the real ~28–31-day, non-calendar-aligned meter-read
   period). PySAM cross-validation = twelve calendar-month windows summed by
   `estimate_annual`. No "calendar vs billing" branch in the core — only the window-list
   generator differs. A calendar month is just a window starting on the 1st.

2. **Money and energy are `Decimal` end to end; JSON carries them as strings.** Not float.
   The 2% bill-match promise plus a TypeScript port sharing JSON test vectors makes exact,
   language-agnostic arithmetic worth more than byte-matching PySAM's C doubles. The PySAM
   gap is bridged with a documented float tolerance, never by adopting float internally.

3. **Refusal is a typed return value, not an exception, and never a partial number.**
   `estimate_bill` returns `BillResult(ok, ...)`; when `ok is False`, `refusal` carries the
   reason and `total is None`. There is **no partial-total mode**. *Malformed* tariffs (bad
   schedule shape, non-monotonic tiers, out-of-range period reference) raise `ValueError` at
   **construction** time. *Well-formed but unpriceable* structures (demand, riders,
   demand-normalized tier maxes, aggregate-usage-across-multiple-periods, $/year-min in one
   window) produce a compute-time `Refusal`. Caller/usage bugs (hourly length ≠ window
   hours) raise `ValueError`.

4. **`$/year` minimum charge is REFUSED in a single bill-match window**, not prorated. An
   annual floor can't be allocated to one month without the full year. It is applied once
   against the 12-window sum inside `estimate_annual`. (Only 4 active-residential rows carry
   a $/year min.)

5. **Day count is a REQUIRED, explicit input**, never inferred. `BillingWindow(start, days)`;
   the `from_dates(start, end)` constructor uses **exclusive end** (`days = (end - start).days`).
   For hourly usage the engine asserts `days == len(hourly_kwh) // 24` and
   `len(hourly_kwh) == days * 24`. `$/day` fixed (141 active-res rows), `$/day` min (43), and
   `kWh daily` tier maxes (136) all depend on it.

6. **Per-period independent tier ladders.** Verified: 499 active-residential TOU/seasonal
   rates have asymmetric tier counts across periods. Each period is its own tuple of tiers;
   tiers never pool across periods. Energy accumulates per period, *then* tiers apply within
   that period — exactly PySAM `ur_ec_tou_mat` semantics.

7. **Frozen dataclasses, zero runtime deps, hand-written `to_json`/`from_json`.** Not
   pydantic (runtime dep + coercion magic). Not bare `TypedDict` (no immutability, no
   construction-time validation). Frozen + slots → immutable, hashable value objects that
   round-trip to plain JSON, so the future TS port shares identical vectors.

8. **Net metering / sell rates are a WARNING, not a refusal** (implementer's refinement of
   the panel's over-conservative "refuse on NEM"). v0 `Usage` expresses **consumption only**
   (kWh ≥ 0, no export), so a sell rate is never applied and the consumption bill is correct.
   Refusing would needlessly break bill-match for any customer on a NEM-flagged default rate.
   The engine emits `net_metering_not_modeled` / `sell_rate_not_modeled` warnings and returns
   `ok=True`. Demand charges and riders DO change the consumption bill and remain refusals.

---

## 1. Module layout (under `packages/ratebook/src/ratebook/`)

- `money.py` — `Decimal` helpers (`to_decimal`), JSON scalar codecs (Decimal↔str, date↔ISO).
- `schema.py` — all frozen dataclasses + `StrEnum`s + `to_json`/`from_json` + construction
  validation. The tariff data model; shared with `ratebook-data` (producer) and the TS port.
- `validate.py` — `Issue` + pure `validate_*` helpers, reused by the extraction grader.
- `engine.py` — `estimate_bill`, `estimate_annual`, `supported`, and internals.
- `urdb.py` — pure `tariff_from_v8(json) -> Tariff` importer (URDB v8 JSON → Tariff).
- `__init__.py` — re-exports the public surface.

`ratebook-data` gets `urdb.row_to_v8(row) -> dict` (un-flatten a `raw.urdb` CSV row into URDB
v8 nested JSON). PySAM is a **test-only** dependency, never imported by the engine.

## 2. Schema (frozen dataclasses, `Decimal` money, JSON-as-string wire format)

Enums (`StrEnum`, closed + `UNKNOWN` where corpus data is dirty): `FixedChargeUnit`
{$/month,$/day}, `MinChargeUnit` {$/month,$/day,$/year}, `TierMaxUnit` {kWh, kWh daily,
kWh/kW, kWh/kVA, kWh/hp, kWh/kW daily}, `DayType` {weekday,weekend}, `HolidayPolicy`
{unknown,as_weekend,as_weekday}, `Sector`, `MeteringOption`, `TariffType`
{bundled,delivery_only,supply_only,unknown}, `SourceType`, `UnsupportedKind`.

Priced core (mirrors `ur_ec_tou_mat` row `[period, tier, max, units, buy_rate, sell_rate]`):
`EnergyTier(rate, adj=0, max=None, max_unit=kWh, sell=None)` — effective rate = `rate+adj`;
`max=None` only on the final (open) tier; `sell` carried, not priced. `EnergyPeriod(tiers)`
— tuple index = the period id the schedules reference. `EnergyRateStructure(periods)`.
`Schedule(weekday, weekend, holiday_policy)` — each matrix exactly 12×24 ints (validated at
construction). `FixedCharge(amount, unit)` (amount may be negative). `MinCharge(amount, unit)`.

Carried-but-unpriced: `UnsupportedFeature(kind, detail)`. Identity/provenance:
`TariffIdentity`, `EffectiveRange(start,end,superseded_at,scheduled_end)` (start≤end),
`SourceDocument(...)`, `Provenance(urdb_label, urdb_latest_update, last_verified, confidence,
snapshot_sha256)`. Top-level `Tariff(identity, effective_range, energy, schedule,
fixed_charges, min_charge, unsupported, metering, source_documents, provenance,
schema_version)`. `__post_init__` raises `ValueError` on malformed structure (shape,
partition, out-of-range period refs).

## 3. Engine API

```
estimate_bill(tariff, usage, window) -> BillResult
estimate_annual(tariff, hourly_kwh_8760, year) -> AnnualResult   # 12 calendar-month windows
supported(tariff) -> SupportReport                                # can/can't price, no compute
```

`Usage(hourly_kwh | total_kwh)` — exactly one set. `BillingWindow(start, days)` +
`from_dates`. `BillResult(ok, total, energy_charge, fixed_charge, min_charge_floor_applied,
line_items, window, warnings, refusal)`. `LineItem(period, tier, kwh, rate, subtotal, note)`.
`Refusal(reason, detail)`. `AnnualResult(total, windows, refusal)`.

## 4. `_price_window` algorithm (deterministic)

1. **Refuse early** if `tariff.unsupported` contains demand/rider/unmodelable kinds; if a
   *used* period has a demand-normalized `TierMaxUnit`; if `$/year` min in a single window.
   (Sell/NEM → warning, not refusal — decision 8.)
2. **Map usage → per-period kWh.** Hourly: for each hour, `day_type` from `date.weekday()`
   (Mon–Fri weekday, Sat/Sun weekend), `period = schedule[day_type][month-1][hour]`,
   accumulate. Aggregate: compute the set of periods the schedule touches over the window's
   date span; size 1 → assign all `total_kwh` to it; size > 1 → `Refusal(aggregate_usage_multi_period)`.
3. **Tiers per period** (decision 6): walk each period's ladder; tier `i` covers cumulative
   in-period usage from `tier[i-1].max` to `tier[i].max` at `rate+adj`; final tier open (a
   finite max on the final tier is treated as open per URDB/PySAM convention, with a
   `usage_exceeds_final_tier_max` warning). `kWh daily` max → `max × active_days`, where
   `active_days` is the number of distinct days *that period* appears in the window — NOT the
   whole window's day count. A weekday-only period accrues its daily allowance on ~22 days of
   a month, a summer period on 0 days of a winter window. (Bounded tiers within a period must
   share one max unit — mixing is rejected at construction.)
4. **Fixed:** `$/month` once per window; `$/day × days`. Signed.
5. **Minimum:** floor = `$/month` as-is, `$/day × days`; total = `max(subtotal, floor)`.
6. Assemble `BillResult` with per-`(period,tier)` line items.

## 5. Validation helpers (shared with the grader, §6 of URDB_NOTES)

`validate_tier_partition`, `validate_schedule_shape`, `validate_period_coverage`
(every referenced period has a rate — the ≥15 dangling-reference check),
`validate_8760_coverage`, `validate_value_ranges`. Each returns `list[Issue]`.

## 6. Property tests (hypothesis)

Monotone non-decreasing total in `total_kwh` (non-negative tariffs); `energy_charge ==
sum(line_items)`; tier-partition coverage (every kWh billed exactly once); linearity within a
tier; determinism (identical input → byte-identical JSON); flat-rate closed form
(`fixed + kwh × (rate+adj)`); window additivity within a reset (two adjacent sub-windows ==
one window when no tier boundary crosses), and deliberately NOT across resets.

## 7. PySAM `utilityrate5` validation

Test-only dep, skipped if `PySAM` not importable. Take real URDB residential tariffs from the
corpus → `row_to_v8` → `tariff_from_v8` → `Tariff`. Build `utilityrate5` inputs directly from
the `Tariff` (`ur_ec_sched_weekday/weekend` 1-indexed, `ur_ec_tou_mat` rows with
`buy_rate = rate+adj` since PySAM has no adj column, `ur_monthly_fixed_charge`, demand
disabled, zero generation so no export). Drive both with an identical synthetic 8760 load;
run `estimate_annual(..., year)` with monthly reset. Assert agreement on **energy charge and
fixed charge separately** (so offsets can't cancel) to `< $0.01` or `< 1e-4` relative.
Empirically probe PySAM's weekday/weekend calendar and align the test year so day-of-week
assumptions match. Freeze agreeing cases as JSON vectors in `tests/vectors/`.

Strata: flat (PECO Rate R), tiered-non-TOU, seasonal-tiered, single-tier TOU, TOU+tiered
(North Central "Residential TOD", eiaid 13693 — verified intra-day TOU with per-period adj).
Refused tariffs (demand/rider) are asserted `ok=False`, not compared.

## 8. Cross-engine test vectors

`tests/vectors/*.json`: `{tariff, usage, window, expected: BillResult}`, all via
`to_json`/`from_json`. The TS port consumes the identical files. Decimal-as-string keeps them
byte-identical across languages.

Corpus-grounded facts baked in: PECO Rate R = single period/tier `0.20513 + 0.01371` with
`$11.30/mo` fixed; tier-max units kWh 5284 / kWh-daily 136 / kWh-per-kW 9 / kWh-per-hp 9;
$/day fixed 141; $/year min 4; negative fixed charges 13.
